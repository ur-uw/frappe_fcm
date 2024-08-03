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
    user_device_id = frappe.get_all(
        "User Device", filters={"user": user_email,"enabled":True}, fields=["device_id","name"]
    )
    return user_device_id


@frappe.whitelist()
def send_notification(doc, event=None):
    if event != None:
        device_ids = user_id(doc)
        for dvs in device_ids:
            enqueue(
                process_notification,
                queue="notifications_queue",
                now=False,
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
        customer_jid = frappe.db.get_value(
            "Customer", sales_order.customer, "jid", debug=True
        )
        sales_partner_jid = frappe.db.get_value(
            "Sales Partner", sales_order.sales_partner, "jid", debug=True
        )
        address = frappe.get_doc("Address", sales_order.customer_address)
        if address and address.custom_latitude:
            data["latitude"] = address.custom_latitude
            data["longitude"] = address.custom_longitude
        if customer_jid:
            data["customer_jid"] = customer_jid
        if sales_partner_jid:
            data["sales_partner_jid"] = sales_partner_jid

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
                        ),
                    )
                ),
                fcm_options=messaging.FCMOptions(
                    analytics_label="assign_agent_to_order",
                ),
            ),
        )
    except messaging.UnregisteredError as e:
        # TODO: optimize this add devices to a list and disable them with frappe.db.set_value then use commit only once
        frappe.db.set_value("User Device", device.name, "enabled", 0)
        frappe.db.commit()
        frappe.error_log(f"Error sending notification: {e}, Disabling Device ID: {device.device_id}")
        return device.device_id
    except Exception as e:
        frappe.error_log(f"Error sending notification: {e}")
        return None