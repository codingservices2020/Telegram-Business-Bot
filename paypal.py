import logging
import requests
import os
import time
from dotenv import load_dotenv
load_dotenv()

# Logger setup
logging.basicConfig(level=logging.INFO)

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET")
PAYPAL_API_BASE = os.getenv("PAYPAL_API_BASE")
BOT_URL = os.getenv("BOT_URL")

# Generate Access Token
def get_paypal_access_token():
    url = f"{PAYPAL_API_BASE}/v1/oauth2/token"
    headers = {"Accept": "application/json", "Accept-Language": "en_US"}
    data = {"grant_type": "client_credentials"}
    response = requests.post(url, headers=headers, data=data, auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET))
    response.raise_for_status()
    return response.json()["access_token"]


# Create PayPal Order
def create_paypal_payment_link(amount, chat_id):
    access_token = get_paypal_access_token()
    url = f"{PAYPAL_API_BASE}/v2/checkout/orders"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    data = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": str(chat_id),
                "custom_id": str(chat_id),  # ✅ used later to verify Telegram user
                "amount": {
                    "currency_code": "USD",
                    "value": str(amount)
                },
                "description": f"Report download for Telegram user {chat_id}"
            }
        ],
        "application_context": {
            # 🔥 UX + Wallet Optimizations
            "brand_name": "Coding Services",
            "landing_page": "LOGIN",              # shows PayPal + wallets first
            "user_action": "PAY_NOW",             # strong CTA
            "shipping_preference": "NO_SHIPPING", # no address form
            "return_url": "https://codingservices2020.github.io/Checkout-Page/",
            "cancel_url": BOT_URL
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        order = response.json()

        approve_url = next(
            link["href"] for link in order["links"]
            if link["rel"] == "approve"
        )

        logging.info(f"✅ PayPal order created: {order['id']} for user {chat_id}")

        return order["id"], approve_url

    except requests.exceptions.HTTPError as e:
        logging.error("❌ Failed to create PayPal order")
        logging.error(e.response.json())
        return None, None



# Capture Payment
def capture_payment(order_id):
    access_token = get_paypal_access_token()
    url = f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        payment_result = response.json()
        status = payment_result['purchase_units'][0]['payments']['captures'][0]['status']  # shows "COMPLETED" if paid successfully
        name = payment_result['payer']['name']['given_name']+" "+payment_result['payer']['name']['surname']
        email = payment_result['payer']['email_address']
        paid_amount = payment_result['purchase_units'][0]['payments']['captures'][0]['amount']['value']
        currency = payment_result['purchase_units'][0]['payments']['captures'][0]['amount']['currency_code']
        user_id = payment_result['purchase_units'][0]['payments']['captures'][0]['custom_id']
        #  Breakdown of amount received by the seller
        seller_receivable_breakdown = payment_result['purchase_units'][0]['payments']['captures'][0]['seller_receivable_breakdown']
        paypal_fee = seller_receivable_breakdown['paypal_fee']['value']
        net_amount = seller_receivable_breakdown['net_amount']['value']

        data = {
            "status": status,
            "name": name,
            "email": email,
            "currency": currency,
            "user_id": user_id,
            "paid_amount": paid_amount,
            "paypal_fee": paypal_fee,
            "net_amount": net_amount  # net_amount received by the seller
        }
        return data
    except requests.exceptions.HTTPError as e:
        print(f"Failed to capture payment: {e.response.json()}")
