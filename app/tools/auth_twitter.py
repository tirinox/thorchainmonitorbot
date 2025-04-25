import asyncio

import tweepy

from comm.twitter.twitter_bot import TwitterBot
from lib.texts import sep
from main import App
from tools.lib.lp_common import LpAppFramework


class AuthTwitterApp(App):
    def __init__(self):
        super().__init__()
        self.twitter_bot = TwitterBot(self.deps.cfg)
        self.twitter_bot.is_mock = False

    async def authorize(self):
        print("This utility will help you authorize the bot so that it can post on your behalf to a specific account.")
        print("First, make sure that you signed up for Twitter Developer Program and created an app.")
        print("👉  https://developer.twitter.com/en/portal/dashboard ")
        print("You will need to obtain the following keys:")
        print("1. Consumer Key")
        print("2. Consumer Secret")
        print("Access token and Access token secret will be generated during the authorization process.")
        print("Now, fill in the following fields in the config.yaml file:")

        sep()
        print("""twitter:
  enabled: true
  is_mock: false

  bot:
    consumer_key: "<---"
    consumer_secret: "<---"
    access_token: "leave blank"
    access_token_secret: "leave blank""")
        sep()

        input("Press Enter to continue...")

        cli = self.twitter_bot.client

        callback_uri = 'oob'
        oauth1_user_handler = tweepy.OAuth1UserHandler(
            cli.consumer_key, cli.consumer_secret,
            callback=callback_uri
        )

        # Get the authorization URL to redirect the user to Twitter
        redirect_url = oauth1_user_handler.get_authorization_url()

        # Redirect the user to the URL where they'll authorize your app
        print("Please visit this URL to authorize your app: ", redirect_url)
        print("You must be logged in to the account you want to authorize.")

        verifier = input("Input PIN: ")
        access_token, access_token_secret = oauth1_user_handler.get_access_token(
            verifier
        )

        print(f'Access token: {access_token}')
        print(f'Access token secret: {access_token_secret}')
        print(f'Your config.yaml file should look like this:')

        sep()
        print(f"""twitter:
  enabled: true
  is_mock: false

  bot:
    consumer_key: "{cli.consumer_key}"
    consumer_secret: "{cli.consumer_secret}"
    access_token: "{access_token}"
    access_token_secret: "{access_token_secret}""")
        sep()


async def main():
    LpAppFramework.solve_working_dir_mess()
    app = AuthTwitterApp()
    await app.authorize()


if __name__ == '__main__':
    asyncio.run(main())
