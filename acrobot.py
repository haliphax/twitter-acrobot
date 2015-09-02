#!/usr/bin/env python
"""
Twitter Acrobot: Play the 'acro' game on Twitter

This bot generates a random acronym and a random hashtag for tracking
individual rounds of play. During the first phase of the round, users may
submit their definitions for the random acronym. Once the second phase begins,
submissions are closed and users may vote for their favorite acronym (only once,
and not for themselves). Once the second phase is complete, the votes are
tallied and a winner is chosen.
"""
__author__ = 'haliphax <https://github.com/haliphax>'

# @TODO scoring mechanism


# Twitter app credentials
TOKEN = 'REDACTED'
TOKEN_KEY = 'REDACTED'
# Twitter account credentials
CONSUMER_SECRET = 'REDACTED'
CONSUMER_SECRET_KEY = 'REDACTED'
# timer settings
POLL_DELAY = 60  # seconds between polling for new @mentions
ROUND_DELAY = 300  # seconds between rounds
PHASE_LENGTH = 20  # length (in minutes) of window for submissions/votes
# other "magic numbers"
MIN_ACRONYMS = 2  # minimum number of acronyms before submissions are closed
MIN_VOTES = 1  # minimum number of votes before final tally can proceed
HASHTAG_KEY_LENGTH = 6  # length of randomized hashtag "key" for round ID
ACRONYM_MIN_LENGTH = 3  # minimum length of generated acronym
ACRONYM_MAX_LENGTH = 5  # maximum length of generated acronym
# statuses
STATUS_START_SUBMIT = 'Acronym: {acronym} #{hashtag}'
STATUS_START_VOTE = 'Submissions closed. Vote for your favorite! {acronym} ' \
                    '#{hashtag}'
STATUS_WINNER = 'Winner! @{user} https://twitter.com/{user}/statuses/{tweet} ' \
                '#{hashtag}'
# direct messages
DM_NO_HASHTAG = 'Wrong hashtag or hashtag not found; submission rejected'
DM_GOOD_ACRONYM = 'Acronym accepted. Reminder: Only your most recent is valid!'
DM_BAD_ACRONYM = 'Bad acronym or acronym not found; submission rejected'
DM_GOOD_VOTE = 'Vote accepted. Reminder: Only your most recent is valid!'
DM_BAD_VOTE = 'Vote rejected; you must vote for a submitter from this round ' \
              'who is not yourself!'


def authenticate():
    """ Setup our authentication and return the OAuth object. """
    from twitter import OAuth

    return OAuth(TOKEN, TOKEN_KEY, CONSUMER_SECRET, CONSUMER_SECRET_KEY)


def get_twitter(auth):
    """ Pull back a Twitter object to use elsewhere. """
    from twitter import Twitter

    return Twitter(auth=auth)


def generate_acronym():
    """ Create a random acronym to use. """
    from string import ascii_uppercase
    from random import choice, randint

    acronym_length = randint(ACRONYM_MIN_LENGTH, ACRONYM_MAX_LENGTH)
    acronym = ''

    for _ in range(acronym_length):
        acronym += choice(ascii_uppercase)

    return acronym


def validate_acronym(acronym, submission):
    """ Validate a submission against the acronym. """
    chunks = submission.split(' ')
    acronym_len = len(acronym)

    # needs to use the right number of words
    if len(chunks) != acronym_len:
        return False

    # first letter of each word needs to match the acronym
    for i in range(acronym_len):
        if chunks[i][0].upper() != acronym[i]:
            return False

    return True


def generate_hashtag():
    """ Create a random hashtag to associate with this session. """
    from string import ascii_letters, digits
    from random import choice

    hashtag = ''

    for _ in range(1, HASHTAG_KEY_LENGTH + 1):
        hashtag += choice(ascii_letters + digits)

    return hashtag


def handle_submissions(twit, since_id, acronym, hashtag):
    """ Parse acronym submissions. """
    import re
    from datetime import datetime, timedelta
    from time import sleep

    start_time = now = datetime.now()
    end_time = start_time + timedelta(minutes=PHASE_LENGTH)
    submissions = dict()
    print('Submission window open')

    # main loop - go until window is closed AND we have at least MIN_ACRONYMS

    while now < end_time and len(submissions) < MIN_ACRONYMS:
        now = datetime.now()
        # grab all mentions since last tweet
        tweets = twit.statuses.mentions_timeline(since_id=since_id)

        for tweet in tweets:
            user = tweet['user']['screen_name']
            since_id = tweet['id']
            has_hashtag = False

            # it needs to have our round-specific hashtag
            for sub_hashtag in tweet['entities']['hashtags']:
                if sub_hashtag['text'] == hashtag:
                    has_hashtag = True
                    break

            if not has_hashtag:
                twit.direct_messages.new(screen_name=user, text=DM_NO_HASHTAG)
                continue

            # they have to submit something, not just mention + hashtag
            sub_acronym = re.sub('[@#][^@# ]+', '', tweet['text']).strip()

            if (not len(sub_acronym) or
                    not validate_acronym(acronym, sub_acronym)):
                twit.direct_messages.new(screen_name=user, text=DM_BAD_ACRONYM)
                continue

            submission = {'user': user,
                          'tweet': tweet['id'],
                          'acronym': sub_acronym}
            # only track their most recent
            submissions[user] = submission
            twit.direct_messages.new(screen_name=user, text=DM_GOOD_ACRONYM)
            print('Received submission from {user}'.format(user=user))

        sleep(POLL_DELAY)

    print('Submission window closed')

    return submissions


def handle_votes(twit, since_id, submissions, hashtag):
    """ Parse acronym votes. """
    from datetime import datetime, timedelta
    from time import sleep

    start_time = now = datetime.now()
    end_time = start_time + timedelta(minutes=PHASE_LENGTH)
    votes = dict()
    keys = submissions.keys()
    print('Voting window open')

    # main loop - go until window is closed AND we have at least MIN_VOTES

    while now < end_time and len(votes) < MIN_VOTES:
        now = datetime.now()
        # grab all mentions since last tweet
        tweets = twit.statuses.mentions_timeline(since_id=since_id)

        for tweet in tweets:
            since_id = tweet['id']
            has_hashtag = False
            mention = None
            user = tweet['user']['screen_name']

            # it needs to have our round-specific hashtag
            for vote_hashtag in tweet['entities']['hashtags']:
                if vote_hashtag['text'] == hashtag:
                    has_hashtag = True
                    break

            if not has_hashtag:
                twit.direct_messages.new(screen_name=user, text=DM_NO_HASHTAG)
                continue

            # can only vote for someone who has submitted this round
            for vote_mention in tweet['entities']['user_mentions']:
                who = vote_mention['screen_name']

                # cannot vote for yourself
                if who in keys and who not in vote_mention:
                    mention = vote_mention['screen_name']
                    break

            if not mention:
                twit.direct_messages.new(screen_name=user, text=DM_BAD_VOTE)
                continue

            votes[user] = mention
            twit.direct_messages.new(screen_name=user, text=DM_GOOD_VOTE)
            print('Received vote for {mention} from {user}'
                  .format(user=user, mention=mention))

        sleep(POLL_DELAY)

    print('Voting window closed')
    # tally up the votes and choose a winner
    tally = dict()
    highest = 0
    winners = list()

    for vote in votes:
        if vote not in tally:
            tally[vote] = 1
        else:
            tally[vote] = tally[vote] + 1

        if tally[vote] > highest:
            highest = tally[vote]

    for user in tally.keys():
        if tally[user] == highest:
            winners.append(submissions[user])

    return winners


def main():
    """ Main loop for bot process. """
    from time import sleep

    auth = authenticate()
    twit = get_twitter(auth)

    while True:
        # generate random acronym and hashtag for this round
        acronym, hashtag = generate_acronym(), generate_hashtag()
        print('NEW ROUND - Acronym: {acronym}, Hashtag: {hashtag}'
              .format(acronym=acronym, hashtag=hashtag))
        since_id = twit.statuses.update(status=STATUS_START_SUBMIT
                                        .format(acronym=acronym,
                                                hashtag=hashtag))
        # poll for submissions
        submissions = handle_submissions(twit, since_id, acronym, hashtag)
        since_id = twit.statuses.update(status=STATUS_START_VOTE
                                        .format(acronym=acronym,
                                                hashtag=hashtag))
        # poll for votes and determine winner
        winners = handle_votes(twit, since_id, submissions, hashtag)
        print('Winner(s): {winners}'.format(winners=', '.join(winners)))

        for winner in winners:
            user = winner['user']
            tweet_id = winner['tweet']
            twit.statuses.update(status=STATUS_WINNER
                                 .format(user=user, hashtag=hashtag,
                                         tweet=tweet_id))

        # wait for next round
        sleep(ROUND_DELAY)


if __name__ == '__main__':
    # run as a program, not loaded as a module - launch the bot
    main()
