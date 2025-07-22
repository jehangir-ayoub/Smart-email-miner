import os
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from msal import ConfidentialClientApplication
import asyncio

load_dotenv()

GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
CALLBACK_URL = os.getenv("WEBHOOK_CALLBACK_URL")
USER_ID = os.getenv("TARGET_USER_ID")
RESOURCE = f"users/{USER_ID}/mailFolders('Inbox')/messages"

current_subscription_id = None
use_fast_scheduler = True

async def get_access_token():
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    authority = f"https://login.microsoftonline.com/{tenant_id}"

    app = ConfidentialClientApplication(
        client_id=client_id,
        authority=authority,
        client_credential=client_secret
    )
    scope = ["https://graph.microsoft.com/.default"]
    result = app.acquire_token_silent(scopes=scope, account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=scope)
    return result.get("access_token")

async def get_existing_subscription(token):
    global current_subscription_id
    response = requests.get(
        f"{GRAPH_API_URL}/subscriptions",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        subscriptions = response.json().get("value", [])
        for sub in subscriptions:
            if sub.get("resource") == RESOURCE:
                current_subscription_id = sub.get("id")
                print(f"Found existing subscription: {current_subscription_id}")
                return True
    return False

async def delete_all_subscriptions(token):
    response = requests.get(
        f"{GRAPH_API_URL}/subscriptions",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code != 200:
        print("Could not fetch subscriptions:", response.text)
        return

    for sub in response.json().get("value", []):
        sub_id = sub.get("id")
        del_resp = requests.delete(
            f"{GRAPH_API_URL}/subscriptions/{sub_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        if del_resp.status_code == 204:
            print(f"Deleted subscription: {sub_id}")
        else:
            print(f"Failed to delete subscription {sub_id}: {del_resp.text}")

async def create_subscription(token):
    global current_subscription_id
    expiration = (datetime.utcnow() + timedelta(hours=40)).isoformat() + "Z"
    body = {
        "changeType": "created",
        "notificationUrl": CALLBACK_URL,
        "resource": RESOURCE,
        "expirationDateTime": expiration,
        "clientState": "aSecretValueToVerifyTheOrigin"
    }

    print("\n Subscription creation payload:")
    print("POST https://graph.microsoft.com/v1.0/subscriptions")
    print(body)

    response = requests.post(
        f"{GRAPH_API_URL}/subscriptions",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body
    )
    if response.status_code == 201:
        current_subscription_id = response.json().get("id")
        print(f"New subscription created: {current_subscription_id}")
        return True
    else:
        print("Subscription creation failed:", response.status_code, response.text)
        return False

async def renew_subscription():
    global current_subscription_id
    if not current_subscription_id:
        print("No subscription ID available to renew.")
        return False

    token = await get_access_token()
    if not token:
        print("No token available for renewal.")
        return False

    expiration = (datetime.utcnow() + timedelta(hours=40)).isoformat() + "Z"
    patch_body = {"expirationDateTime": expiration}

    response = requests.patch(
        f"{GRAPH_API_URL}/subscriptions/{current_subscription_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=patch_body
    )

    if response.status_code == 200:
        print(f" Subscription {current_subscription_id} renewed until {expiration}")
        return True
    else:
        print(f" Renewal failed for {current_subscription_id}: {response.text}")
        return False

def start_scheduler():
    scheduler = BackgroundScheduler()

    def scheduled_check():
        asyncio.run(run_scheduled_check())

    async def run_scheduled_check():
        global use_fast_scheduler
        print("Running scheduled subscription check...")

        if current_subscription_id:
            success = await renew_subscription()
            if success and use_fast_scheduler:
                use_fast_scheduler = False
                scheduler.remove_job("scheduled_check")
                scheduler.add_job(scheduled_check, "interval", hours=40, id="scheduled_check")
                print("Switched to 40-hour patching schedule.")
            return

        token = await get_access_token()
        if not token:
            print("Failed to get token for recovery.")
            return

        await delete_all_subscriptions(token)
        created = await create_subscription(token)
        if created:
            print("Subscription recovery succeeded. Attempting initial patch...")
            await renew_subscription()

    # Start with fast 30-sec scheduler
    scheduler.add_job(scheduled_check, "interval", seconds=15, id="scheduled_check")
    scheduler.start()
    print("Auto-renew scheduler started (every 15 seconds until first patch, then every 40 hours).")
