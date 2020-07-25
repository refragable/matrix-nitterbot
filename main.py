#   Copyright 2020 Brendan Abolivier <github@brendanabolivier.com>
#   Copyright 2020 A Mak <refragable@mailbox.org>
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import asyncio
import datetime
import time
import typing

import nio
import twitter
import yaml

import requests
from bs4 import BeautifulSoup

# "Easier way to enable verbose logging"
# https://stackoverflow.com/a/20663028
# keep this block disabled unless needed for development purposes
#import argparse
#import logging
#parser = argparse.ArgumentParser()
#parser.add_argument(
#    '-d', '--debug',
#    help="Print lots of debugging statements",
#    action="store_const", dest="loglevel", const=logging.DEBUG,
#    default=logging.WARNING,
#)
#parser.add_argument(
#    '-v', '--verbose',
#    help="Be verbose",
#    action="store_const", dest="loglevel", const=logging.INFO,
#)
#args = parser.parse_args()    
#logging.basicConfig(level=args.loglevel)

with open("config.yaml", "rb") as fp:
    config = yaml.safe_load(fp.read())

screen_name, slug = config["twitter"]["list_full_name"].split("/")

hashtag = config["twitter"].get("hashtag")  # type: typing.Optional[str]
if hashtag:
    hashtag = hashtag.replace("#", "").lower()


def init_twitter():
    cli = twitter.Api(
        consumer_key=config["twitter"]["app"]["consumer_key"],
        consumer_secret=config["twitter"]["app"]["consumer_secret"],
        access_token_key=config["twitter"]["app"]["access_token"],
        access_token_secret=config["twitter"]["app"]["access_token_secret"],
        tweet_mode="extended",
    )

    try:
        # Get an initial list of tweets.
        timeline = cli.GetListTimeline(
            slug=slug,
            owner_screen_name=screen_name,
        )
        # Attempt to extract the tweet ID to start looking from.
        since_id = timeline[0].id if len(timeline) else None
        #log("Initial Timeline loaded")
        return cli, since_id
    except twitter.TwitterError as e:
        # We want to catch the "unknown list" error, which error code is 34 according to
        # https://developer.twitter.com/en/docs/basics/response-codes
        # We also need to do a type check on the error's message's type because the use
        # of TwitterError is inconsistent, see
        # https://github.com/bear/python-twitter/issues/658
        if not isinstance(e.message, list) and e.message[0]["code"] != 34:
            raise

        # If the list couldn't be found, get the existing lists for this screen name, so
        # we can show a helpful message to the user.
        lists = cli.GetLists(screen_name=screen_name)
        slugs = []
        for l in lists:
            slugs.append(l.slug)

        # Log a message to tell the user what lists exist for this screen name so they
        # can easily fix their config.
        log(
            "Couldn't find the list. The existing lists for {screen_name} are: {slugs}"
            .format(screen_name=screen_name, slugs=", ".join(slugs))
        )

        return None, None


async def init_matrix():
    cli = nio.AsyncClient(
        homeserver=config["matrix"]["hs_url"],
        user=config["matrix"]["mxid"],
    )

    await cli.login(config["matrix"]["password"])

    # If the user isn't in the room, join it.
    room_id = config["matrix"]["room_id"]
    res = await cli.joined_rooms()
    if room_id not in res.rooms:
        await cli.join(room_id)

    return cli


def replace_nitter_href(href):
    return href.replace('href="/', 'href="https://nitter.net/')


def parse_nitter_text(tweet):
    url = "https://nitter.net/{screen_name}/status/{id}".format(
        screen_name=tweet.user.screen_name, id=tweet.id,
    )
    #log("Attempting to parse status: %s" % url)
    page = requests.get(url)
    page.encoding = 'utf-8'

    soup = BeautifulSoup(page.text, "html.parser")
    soup.select_one("p.tweet-published").decompose()
    inner_html = soup.select_one("div#m.main-tweet > div.timeline-item > div.tweet-body")
    inner_html.select_one("div.tweet-header").decompose()
    inner_html.select_one("div.tweet-stats").decompose()
    # handle link cards
    try:
        card = inner_html.select_one("div.card")
    except AttributeError:
        card = None
    else:
        if card is not None:
            inner_html.select_one("div.card").decompose()
            #log("Decomposed card for %s" % url)
    # remove some extraneous information from quoted tweets
    try:
        quote = inner_html.select_one("div.quote-big")
    except AttributeError:
        quote = None
    else:
        if quote is not None:
            inner_html.select_one("img.mini.avatar").decompose()
            inner_html.select_one("a.fullname").decompose()
            inner_html.select_one("span.tweet-date").decompose()
            QuoteTag1 = soup.new_tag("i")
            QuoteTag1.string = "Quoted Tweet as follows:"
            inner_html.select_one("a.quote-link").append(QuoteTag1)
            QuoteTag2 = soup.new_tag("i")
            QuoteTag2.string = "Original Status Link:"
            inner_html.select_one("div.tweet-body").append(QuoteTag2)
            #log("Decomposed quote elements for %s" % url)
    # notify users that there are attachments
    # https://www.crummy.com/software/BeautifulSoup/bs4/doc/#append
    # uses extract() to avoid need for decompose()
    try:
        attachment = inner_html.select_one("div.attachments").extract()
    except AttributeError:
        attachment = None
    else:
        if attachment is not None:
            AttachmentTag = soup.new_tag("i")
            AttachmentTag.string = "Tweet attachment(s) found, click on the Nitter link below to view."
            inner_html.append(AttachmentTag)
            #log("Decomposed attachment div for %s" % url)

    html = replace_nitter_href(str(inner_html))

    return html


def build_event_content(tweet):
    # Build the tweet's URL, which incorporates the following format:
    # https://twitter.com/user/status/0123456789
    # nitter URLs look like:
    # https://nitter.net/user/status/0123456789
    url = "https://nitter.net/{screen_name}/status/{id}".format(
        screen_name=tweet.user.screen_name, id=tweet.id,
    )

    # Build a basic body of the message.
    raw_body = '{user_name}: {text} - {url}'.format(
        user_name=tweet.user.name,
        #text=parse_nitter_text(tweet),
        text=tweet.full_text,
        url=url,
    )
    content = {"msgtype": "m.notice", "body": raw_body}

    # Add some HTML formatting if the config includes a template.
    notice_template = config["matrix"].get("notice_template")
    if notice_template:
        formatted_body = notice_template.format(
            user_name=tweet.user.name,
            screen_name=tweet.user.screen_name,
            #text=tweet.full_text.replace("\n", "<br/>"),
            text=parse_nitter_text(tweet),
            url=url,
        )

        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = formatted_body

    return content


def hashtag_in_tweet(tweet):
    in_tweet = False
    # Loop over the tweet's hashtags and check if the text of one matches the one
    # included in the configuration file.
    for tweet_hashtag in tweet.hashtags:
        if tweet_hashtag.text.lower() == hashtag:
            in_tweet = True
    return in_tweet


def log(msg):
    now_iso = datetime.datetime.now().isoformat()
    print("%s - %s" % (now_iso, msg))


async def loop():
    twitter_client, since_id = init_twitter()
    matrix_client = await init_matrix()

    if twitter_client is None or matrix_client is None:
        log("Initialisation failed")
        exit(1)

    log("Initialisation complete")

    while True:
        # The /lists/statuses Twitter API endpoint is rate-limited to 900 requests
        # every 15min, which amounts to a request every second. Sleeping for a second
        # here is a simple and easy way of avoiding getting rate-limited. It means
        # we're not getting the tweets as soon as possible because the request will
        # take more than 0ms, but we don't really care being a few ms behind.
        time.sleep(5) # changed from 1 to 5 in order to use multiple bots.

        # Get the latest tweets in the list. If an error happened, loop over it.
        try:
            timeline = twitter_client.GetListTimeline(
                slug=slug,
                owner_screen_name=screen_name,
                since_id=since_id,
                include_rts=0, # exclude retweets. Comment line to enable retweets
            )
        except twitter.TwitterError as e:
            log("Twitter API returned an error: %s" % e.message)
            continue
        except Exception as e:
            log("An error happened: %s" % e)
            continue

        # If no tweet was returned, loop over.
        if not len(timeline):
            continue

        since_id = timeline[0].id

        # Reverse the list so we're processing tweets in chronological order.
        timeline.reverse()

        # Iterate over the tweets.
        for tweet in timeline:
            # If a hashtag was provided and the tweet doesn't include it, pass over this
            # tweet.
            if hashtag and not hashtag_in_tweet(tweet):
                continue

            # Send the tweet as a notice to the Matrix room.
            content = build_event_content(tweet)
            await matrix_client.room_send(
                room_id=config["matrix"]["room_id"],
                message_type="m.room.message",
                content=content,
            )

            log("Sent notice for tweet %s" % tweet.id)

asyncio.get_event_loop().run_until_complete(loop())
