import logging
import os
from decimal import Decimal

import schedule
from coinbase.wallet.client import Client
from slackclient import SlackClient

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s | %(levelname)s | %(funcName)s |%(message)s')
log = logging.getLogger(__name__)
client = Client(os.environ.get('COINBASE_KEY'), os.environ.get('COINBASE_SECRET'))
slack = SlackClient(os.environ.get('POOKIE_SLACK_TOKEN', 'POOKIE2_SLACK_TOKEN'))
CHANNEL = 'crypt_o_wallet'
USERNAME = 'CryptMoney'
ICON_URL = 'https://cdn.pixabay.com/photo/2013/12/08/12/12/bitcoin-225079_960_720.png'


class WalletService(object):
    invested = 0
    balance = 0
    diff = 0
    _old_diff = 0
    hasChanged = False

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
        difference = old_balance - new_balance
        if difference < Decimal(0):
            return True
        return False

    def percent_changed(self, original_value, new_value):
        return (float(new_value) - float(original_value)) / float(abs(original_value)) * 100

    def run(self):
        log.info("Initializing WalletService")
        schedule.every(1).minutes.do(self.get_summary, notify=True)
        while True:
            schedule.run_pending()

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
        log.info("Total Investment: {}".format(total))
        return total

    def get_total_wallet(self):
        total = Decimal(0)
        message = []
        accounts = client.get_accounts()
        for wallet in accounts.data:
            message.append(str(wallet['name']) + ' ' + str(wallet['native_balance']))
            value = str(wallet['native_balance']).replace('USD', '')
            total += Decimal(value)
        log.info("Total Balance: {}".format(total))
        return total

    def get_summary(self, notify=False):
        log.info("Collecting Summary data")
        self.hasChanged = False
        self.invested = self.get_total_invested()
        self.balance = self.get_total_wallet()
        self.diff = self.difference(self.balance, self.invested)
        self.percent = self.percent_changed(self.invested, self.balance)
        gained = self.gained(self.balance, self.invested)
        if self.diff != self._old_diff:
            log.info("Found diffs between current <{}> and old <{}>".format(self.diff, self._old_diff))
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
        if notify and self.hasChanged:
            slack.api_call("chat.postMessage", text="",
                           icon_url=ICON_URL,
                           attachments=summary_message['attachments'], channel=CHANNEL, username=USERNAME,
                           as_user=False)
            if self.percent >= 10 or self.percent <= -10:
                pass
        return results


service = WalletService()
if __name__ == '__main__':
    service.run()
