# Nitterbot for Matrix

A simplistic [Matrix](https://matrix.org) bot for Twitter-backed
watchalongs. It posts statuses from Nitter.

Available on:  
[Github](https://github.com/refragable/matrix-nitterbot) - [Gitlab](https://gitlab.com/refragable/matrix-nitterbot) - Sourcehut [Project](https://sr.ht/~refragable/nitterbot-matrix/)/[Repo](https://git.sr.ht/~refragable/nitterbot-matrix)

## How it works

Every five seconds, the bot polls new tweets from a given Twitter list and
sends the Nitter version (unshortened URLs and all URLs rewritten to nitter.net) to a given Matrix room. If a hashtag is also provided, only
tweets containing the hashtag (regardless of case) will be sent.

## Install

```bash
# Clone the repository
git clone https://github.com/refragable/matrix-nitterbot.git
cd matrix-tweetalong-bot
# Create a virtualenv
python3 -m venv env
. env/bin/activate
# Install the dependencies
pip install -r requirements.txt
# When you're finished
deactivate
```

## Configure

Copy [`config.sample.yaml`](/config.sample.yaml) into `config.yaml`.
This sample configuration includes comments documenting how to configure
the bot.

## Run

It is best to run this bot in a screen/tmux session on a server. That way it will run 24/7.

```bash
. env/bin/activate
python3 main.py
```

## Sample Systemd Service

A Systemd service will run the bot automatically on (re)boot and restart it if the process dies. This requires an account with `sudo` permissions.

Create a shell script `start.sh`:

```bash
#!/bin/bash
cd <path to nitterbot directory>
. env/bin/activate
python3 main.py
```
Then create the following `nitterbot.service` file:

```
[Unit]
Description=Nitterbot for Matrix
After=network.target
StartLimitIntervalSec=0
[Service]
Type=simple
User=<user>
Group=<user>
WorkingDirectory=/home/user/nitterbot/
ExecStart=/home/user/nitterbot/start.sh
Restart=always
RestartSec=5
RuntimeMaxSec=604800
[Install]
WantedBy=multi-user.target
```
Then run the following to install the service file:
1. `sudo cp nitterbot.service /etc/systemd/system/`
2. `sudo systemctl enable nitterbot.service`
3. `sudo systemctl start nitterbot.service`

## Credits

Brendan Abolivier - [Matrix Tweetalong bot](https://github.com/babolivier/matrix-tweetalong-bot)

Ilya Pupko - [TwitterStatic](https://github.com/ILAsoft/TwitterStatic) for the Nitter parsing.
