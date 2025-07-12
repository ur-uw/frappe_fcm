# Copyright (c) 2022, Raheeb and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class UserDevice(Document):
    pass


@frappe.whitelist()
def handle_user_device(device_data):
    device_id = device_data.get("device_id")
    if not device_id:
        frappe.throw(frappe._("Device ID is required"))
    if frappe.db.exists("User Device", {"device_id": device_id}):
        # Update the existing record
        user_device = frappe.get_doc("User Device", {"device_id": device_id})
        user_device.update(device_data)
        user_device.save(ignore_permissions=True)
        frappe.db.commit()
        return user_device
    user_device = frappe.new_doc("User Device")
    user_device.update(device_data)
    user_device.save(ignore_permissions=True)
    frappe.db.commit()
    return {
        "device_id": user_device.device_id,
        "result": "success"
    }
