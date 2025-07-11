import re

import firebase_admin
import frappe
from firebase_admin import credentials, messaging
from frappe import enqueue


def initialize_firebase():
    firebase_settings = frappe.get_single("Firebase Settings")
    service_account = firebase_settings.service_account
    try:
        admin = firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(frappe.get_site_path() + service_account)
        firebase_admin.initialize_app(cred)


def user_id(doc):
    user_email = doc.for_user
    user_device_id = get_user_devices(user_email)
    return user_device_id


def get_user_devices(user):
    """Get all enabled devices for a user."""
    return frappe.get_all(
        "User Device",
        filters={"user": user, "enabled": True},
        fields=["device_id", "name"],
    )


@frappe.whitelist()
def send_notification(doc, event=None):
    if event != None:
        device_ids = user_id(doc)
        for dvs in device_ids:
            enqueue(
                process_notification,
                queue="notifications_queue",
                device=dvs,
                notification=doc,
            )


def convert_message(message):
    CLEANR = re.compile("<.*?>")
    cleanmessage = re.sub(CLEANR, "", message)
    # cleantitle = re.sub(CLEANR, "",title)
    return cleanmessage


def process_notification(device, notification):
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
    # Get customer address lat, long and send it to the agent via notification if the doctype is SalesOrder
    if notification.document_type == "Sales Order":
        sales_order = frappe.get_doc("Sales Order", notification.document_name)
        address = frappe.get_cached_doc("Address", sales_order.customer_address)
        if address and address.custom_latitude:
            data["latitude"] = address.custom_latitude
            data["longitude"] = address.custom_longitude
        send_fcm_message(device, title, message, data)


def send_fcm_message(device, title, message, data):
    initialize_firebase()
    """Send FCM notification to a specific device"""
    try:
        messaging.send(
            message=messaging.Message(
                data=data,
                token=device.device_id,
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
                            custom_data=data,
                        ),
                    )
                ),
                fcm_options=messaging.FCMOptions(
                    analytics_label="assign_agent_to_order",
                ),
            ),
        )
    except messaging.UnregisteredError as e:
        frappe.db.set_value("User Device", device.name, "enabled", 0)
        frappe.db.commit()
        frappe.log_error(
            title="Unregistered Device",
            message=f"Device {device.device_id} is unregistered. Error: {str(e)}",
            reference_doctype="User Device",
            reference_name=device.name,
        )
        return device.device_id
    except Exception as e:
        frappe.error_log(f"Error sending notification: {e}")
        return None
