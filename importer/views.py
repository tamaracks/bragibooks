from django.shortcuts import render, redirect
import importlib, json, logging, os, requests
from pathlib import Path
# from login.models import User
from .models import Book, Author, Narrator, Genre
# core merge logic:
from .merge_cli import *
from django.contrib import messages
# To display book length
from datetime import timedelta

# Get an instance of a logger
logger = logging.getLogger(__name__)

import os

# Set environment variable DJANGO_LOG_LEVEL to desired level
# https://docs.djangoproject.com/en/2.2/topics/logging/

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# If using docker, default to /input folder, else $USER/input
if Path('/input').is_dir():
	rootdir = Path('/input')
else:
	rootdir = f"{str(Path.home())}/input"

def importer(request):
	folder_arr = []
	for path in sorted(Path(rootdir).iterdir(), key=os.path.getmtime, reverse=True):
		base = os.path.basename(path)
		folder_arr.append(base)

	context = {
		"this_dir": folder_arr,
	}
	return render(request, "importer.html", context)

def dir_selection(request):
	request.session['input_dir'] = request.POST.getlist('input_dir')
	return redirect('/import/match')

def match(request):
	context_item = request.session['input_dir']

	context = {
		"this_input": context_item
	}
	
	return render(request, "match.html", context)

def make_models(asin, input_data):
	metadata = audible_parser(asin)
	m4b_data(input_data, metadata, output)

	## Book DB entry
	if 'subtitle' in metadata:
		base_title = metadata['title']
		base_subtitle = metadata['subtitle']
		title = f"{base_title} - {base_subtitle}"
	else:
		title = metadata['title']

	new_book = Book.objects.create(
		title=metadata['title'],
		asin=asin,
		short_desc=metadata['short_summary'],
		long_desc=metadata['long_summary'],
		release_date=metadata['release_date'],
		publisher=metadata['publisher_name'],
		lang=metadata['language'],
		runtime_length_minutes=metadata['runtime_length_min'],
		format_type=metadata['format_type'],
		converted=True,
		src_path=input_data[0],
		dest_path=(
		f"\""
		f"{output}/"
		f"{metadata['authors'][0]}/"
		f"{metadata['title']}/"
		f"{title}.m4b"
		f"\""
		)
		)

	# Only add in series if it exists
	if 'series' in metadata:
		new_book.series = metadata['series']

	new_book.save()

	## Author DB entry
	# Create new entry for each author if there's more than one
	if len(metadata['authors']) > 1:
		for author in metadata['authors']:
			author_name_split = author['name'].split()
			last_name_index = len(author_name_split) - 1

			# Check if author asin exists
			if 'asin' in author:
				author_asin = author['asin']
				_filter_vals = {'asin': author_asin}
			# If author doesn't exist, search by name and set asin to none
			else:
				author_asin = None
				_filter_vals = {'first_name': author_name_split[0], 'last_name': author_name_split[last_name_index]}
				logger.warning(f"No author ASIN for: {author['name']}")

			# Check if author is in database
			if not Author.objects.filter(
				**_filter_vals
			):
				new_author = Author.objects.create(
					asin=author_asin,
					first_name=author_name_split[0],
					last_name=author_name_split[last_name_index]
				)
				new_author.books.add(new_book)
				new_author.save()
			else:
				author_id = Author.objects.filter(
					**_filter_vals
				)
				existing_author = Author.objects.get(
					id = author_id[0].id
				)
				existing_author.books.add(new_book)
				existing_author.save()
	else:
		author_name_split = metadata['authors'][0]['name'].split()
		last_name_index = len(author_name_split) - 1

		# Check if author asin exists
		if 'asin' in metadata['authors'][0]:
			author_asin = metadata['authors'][0]['asin']
			_filter_vals = {'asin': author_asin}
		# If author doesn't exist, search by name and set asin to none
		else:
			author_asin = None
			_filter_vals = {'first_name': author_name_split[0], 'last_name': author_name_split[last_name_index]}
			logger.warning(f"No author ASIN for: {metadata['authors'][0]['name']}")

		# Check if author is in database
		if not Author.objects.filter(
			**_filter_vals
		):
			new_author = Author.objects.create(
				asin=author_asin,
				first_name=author_name_split[0],
				last_name=author_name_split[last_name_index]
			)
			new_author.books.add(new_book)
			new_author.save()
		else:
			author_id = Author.objects.filter(
				**_filter_vals
			)
			existing_author = Author.objects.get(
				id = author_id[0].id
			)
			existing_author.books.add(new_book)
			existing_author.save()

	## Narrator DB entry
	# Create new entry for each narrator if there's more than one
	if len(metadata['narrators']) > 1:
		for narrator in metadata['narrators']:
			narr_name_split = narrator.split()
			last_name_index = len(narr_name_split) - 1
			if not Narrator.objects.filter(
				first_name=narr_name_split[0],
				last_name=narr_name_split[last_name_index]
			):
				new_narrator = Narrator.objects.create(
					first_name=narr_name_split[0],
					last_name=narr_name_split[last_name_index]
				)
				new_narrator.books.add(new_book)
				new_narrator.save()
			else:
				existing_narrator = Narrator.objects.get(
					first_name=narr_name_split[0],
					last_name=narr_name_split[last_name_index]
				)
				existing_narrator.books.add(new_book)
				existing_narrator.save()
	else:
		narr_name_split = metadata['narrators'][0].split()
		last_name_index = len(narr_name_split) - 1
		if not Narrator.objects.filter(
			first_name=narr_name_split[0],
			last_name=narr_name_split[last_name_index]
		):
			new_narrator = Narrator.objects.create(
				first_name=narr_name_split[0],
				last_name=narr_name_split[last_name_index]
			)
			new_narrator.books.add(new_book)
			new_narrator.save()
		else:
			existing_narrator = Narrator.objects.get(
				first_name=narr_name_split[0],
				last_name=narr_name_split[last_name_index]
			)
			existing_narrator.books.add(new_book)
			existing_narrator.save()
		
def api_auth(request):
	return render(request, "authenticate.html")

def get_auth(request):
	audible_login(
		USERNAME=request.POST['aud_email'],
		PASSWORD=request.POST['aud_pass'])
	return redirect('/import/match')

def get_asin(request):
	#check that user is signed into audible api
	auth_file = Path(dir_path, ".aud_auth.txt")
	if not auth_file.exists():
		return redirect('/import/api_auth')

	asin_arr = []
	dict1 = request.POST
	for key, value in dict1.items():
		if key != "csrfmiddlewaretoken":
			asin = value
			asin_key = int(key[5:7])
			input_data = get_directory(
				f"{rootdir}/{request.session['input_dir'][asin_key]}"
				)
			# Check for validation errors
			errors = Book.objects.book_asin_validator(asin)
			if len(errors) > 0:
				for k, v in errors.items():
					messages.error(request, v)
				return redirect('/import/match')
			else:
				# Check that asin actually returns data from audible
				check = requests.get(f"https://www.audible.com/pd/{asin}")
				if check.status_code == 200:
					asin_arr.append(asin)
					logger.info(f"Validated ASIN: {asin}")
					# make_models(asin, input_data)
				else:
					logger.error(f'Got http error: {check.status_code}')
					return redirect('/import/match')

	for i in range(len(asin_arr)):
		input_data = get_directory(
				f"{rootdir}/{request.session['input_dir'][i]}"
				)
		logger.info(f"Making models and merging files for: {input_data}")
		make_models(asin_arr[i], input_data)

	request.session['asins'] = asin_arr
	return redirect('/import/confirm')

def finish(request):
	asins = request.session['asins']
	this_book = Book.objects.filter(asin__in=asins)

	length_arr = []
	for book in this_book:
		d = timedelta(minutes=book.runtime_length_minutes)
		book_length_calc = (
			f'{d.seconds//3600} hrs and {(d.seconds//60)%60} minutes'
		)
		length_arr.append(book_length_calc)

	print(length_arr)

	context = {
		"finished_books": this_book,
		"book_lengths": length_arr
	}
	
	return render(request, "finish.html", context)