import logging
import os
import sys
import traceback
from decimal import Decimal

import schedule
from coinbase.wallet.client import Client
from slackclient import SlackClient

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s | %(levelname)s | %(funcName)s |%(message)s')
log = logging.getLogger(__name__)
client = Client(os.environ.get('COINBASE_KEY'), os.environ.get('COINBASE_SECRET'))
slack = SlackClient(os.environ.get('POOKIE_SLACK_TOKEN'))
CHANNEL = '#crypt_o_wallet'
CHANNEL_ID = "CLE5A5GJC"
USERNAME = 'CryptMoney'
ICON_URL = 'https://cdn.pixabay.com/photo/2013/12/08/12/12/bitcoin-225079_960_720.png'
ALIAS = 'cryptobot'


class WalletService(object):
    def __init__(self):
        self.invested = 0
        self.balance = 0
        self.diff = 0
        self._old_diff = 0
        self.hasChanged = False
        self.REQUESTS = {
            'get details': {
                'action': self.send_details
            },
        }

    def my_account_data(self):
        my_accounts = []
        accounts = client.get_accounts()
        for account in accounts.data:
            if str(account.native_balance.amount) != '0.00':
                my_accounts.append(account)
        return my_accounts

    def difference(self, last_price, new_price):
        return last_price - new_price

    def gained(self, new_balance, old_balance):
        difference = self.difference(old_balance, new_balance)
        if difference < Decimal(0):
            return True
        return False

    def percent_changed(self, original_value, new_value):
        return (float(new_value) - float(original_value)) / float(abs(original_value)) * 100

    def run(self):
        log.info("Initializing WalletService")
        if slack.rtm_connect():
            while True:
                all_data = slack.rtm_read()
                for data in all_data:
                    log.info(data)
                    try:
                        if (data.has_key('text')) and (ALIAS.lower() in data['text']) and (
                                data['channel'] == CHANNEL_ID):
                            self.listen_for_valid_request(data)
                    except Exception as e:
                        ("Uh ohhh. Exceptions\n{}".format(e))
                        self.post_message("Exception: {}\n```{}```".format(e, traceback.print_exc(file=sys.stdout)),
                                          CHANNEL)

    def get_all_transactions(self):
        transactions = []
        accounts_ids = [account.id for account in self.my_account_data()]
        for i in accounts_ids:
            transactions.append(client.get_transactions(i))
        return transactions

    def get_total_invested(self):
        total = Decimal(0)
        transactions = self.get_all_transactions()
        for transaction in transactions:
            for data in transaction.data:
                total += Decimal(data.native_amount.amount)
        return total

    def get_total_wallet(self):
        total = Decimal(0)
        accounts = client.get_accounts()
        for wallet in accounts.data:
            value = str(wallet['native_balance']).replace('USD', '')
            total += Decimal(value)
        return total

    def get_summary(self, notify=False):
        log.info("Collecting Summary data")
        self.hasChanged = False
        self.invested = self.get_total_invested()
        self.balance = self.get_total_wallet()
        self.diff = self.difference(self.balance, self.invested)
        self.percent = self.percent_changed(self.invested, self.balance)
        gained = self.gained(self.balance, self.invested)
        if self.diff == self._old_diff:
            log.info("No Changes. Current Profit: {} | Old Profit: {}".format(self.diff, self._old_diff))
        else:
            log.info("Wallet Balance Changed\nCurrent <{}>\nPrevious <{}>".format(self.diff, self._old_diff))
            self.hasChanged = True
            self._old_diff = self.diff
        results = {
            "Invested": self.invested,
            "Balance": self.balance,
            "Diff": self.diff,
            "byPercent": self.percent
        }
        summary_message = {
            "attachments": [
                {
                    "color": "#36a64f" if gained else '#d90f0f',
                    "blocks": [{
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": "*Total Invested:*\n${}".format(results["Invested"])
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Current Balance:*\n${}".format(results["Balance"])
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Total Profit*\n${}".format(results["Diff"])
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Percent Change*\n{}%".format(round(results["byPercent"], 2))
                            },
                        ]
                    }]
                }
            ]
        }
        log.info("Summary Result:\n{}".format(results))
        if notify and self.hasChanged:
            slack.api_call("chat.postMessage", text="",
                           icon_url=ICON_URL,
                           attachments=summary_message['attachments'], channel=CHANNEL, username=USERNAME,
                           as_user=False)
            if self.percent >= 10 or self.percent <= -10:
                pass
        return results

    def listen_for_valid_request(self, data):
        for command in self.REQUESTS.keys():
            if command in data['text']:
                self.REQUESTS[command].get('action')()
                return command

    def send_details(self, notify=True):
        data = self.my_account_data()
        # message = {
        #     "attachments": [{
        #         "color": "",
        #         "blocks": [{
        #             "type": "section",
        #             "fields": []
        #         }]
        #     }]
        # }
        for detail in data:
            detail_message = {
                "attachments": [
                    {
                        "color": "#36a64f",
                        "blocks": [{
                            "type": "section",
                            "fields": [
                                {
                                    "type": "mrkdwn",
                                    "text": "*Wallet:*\n{}".format(detail.currency)
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": "*Balance:*\n{}".format(detail.native_balance.amount)
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": "*Units:*\n{}".format(detail.balance.amount)
                                }
                            ]
                        },
                            {
                                "type": "divider"
                            }
                        ]
                    }
                ]
            }
            if notify:
                slack.api_call("chat.postMessage", text="", attachments=detail_message['attachments'],
                               username=USERNAME,
                               channel=CHANNEL)
        return data

    # TODO: Use this for all slack messages but with an attachments kwarg
    def post_message(self, channel, text):
        logging.info("Posting Message to Slack")
        logging.info(80 * "=")
        slack.api_call("chat.postMessage", channel=channel, text=text,
                       username=USERNAME, unfurl_links="true")


service = WalletService()


class SlackService(object):
    if __name__ == '__main__':
        schedule.every(5).minutes.do(service.get_summary, notify=True)
        schedule.run_pending()
        log.info(schedule.jobs)
        service.run()
