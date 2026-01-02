# ao3_random_work_generator
use to generate a random work on ao3 if you feel overwhelmed by the choice

how it works

uses playwright to run ao3 searches in a real browser, which avoids the usual rate limits and empty-result issues you get with bots.

it picks a random results page, then a random work from that page.

features

fandom autocomplete

actual randomness (not just sorting by date)

minimal UI

setup
deploy

tested on render’s free tier.

fork the repo

create a new web service on render

connect the repo

select docker runtime

set an env var SECRET_KEY (any value)

deploy

free tier services sleep after inactivity.

local

to run locally:

pip install -r requirements.txt
playwright install chromium
python app.py


runs on http://localhost:5000
.

not affiliated with the otw or ao3.
