import re

import firebase_admin
import frappe
import requests
from firebase_admin import credentials, messaging
from frappe import enqueue


def initialize_firebase():
    try:
        admin = firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(
            frappe.get_site_path() + "/private/files/credentials.json"
        )
        firebase_admin.initialize_app(credential=cred)


def user_id(doc):
    user_email = doc.for_user
    user_device_id = frappe.get_all(
        "User Device", filters={"user": user_email}, fields=["device_id"]
    )
    return user_device_id


@frappe.whitelist()
def send_notification(doc, event=None):
    if event != None:
        device_ids = user_id(doc)
        for device_id in device_ids:
            enqueue(
                process_notification,
                queue="default",
                now=False,
                device_id=device_id,
                notification=doc,
                job_id=device_id.device_id,
            )


def convert_message(message):
    CLEANR = re.compile("<.*?>")
    cleanmessage = re.sub(CLEANR, "", message)
    # cleantitle = re.sub(CLEANR, "",title)
    return cleanmessage


def process_notification(device_id, notification):
    initialize_firebase()
    message = notification.email_content
    title = notification.subject
    if message:
        message = convert_message(message)
    if title:
        title = convert_message(title)
    data = {
        "doctype": notification.document_type,
        "docname": notification.document_name,
        "title": title,
        "message": message,
    }

    try:
        messaging.send(
            message=messaging.Message(
                data=data,
                token=device_id.device_id,
                android=messaging.AndroidConfig(
                    priority="normal",
                    notification=messaging.AndroidNotification(
                        title=title,
                        body=message,
                        channel_id="high_importance_channel",
                    ),
                    fcm_options=messaging.AndroidFCMOptions(
                        analytics_label="assign_agent_to_order",
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(title=title, body=message),
                            sound="default",
                        ),
                    )
                ),
                fcm_options=messaging.FCMOptions(
                    analytics_label="assign_agent_to_order",
                ),
            ),
        )
    except Exception as e:
        frappe.error_log(f"Error sending notification: {e}")
        pass
