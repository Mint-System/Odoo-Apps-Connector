def display_notification(title, message, type):
    return {
        "type": "ir.actions.client",
        "tag": "display_notification",
        "params": {
            "title": title,
            "type": type,
            "message": message,
            "next": {
                "type": "ir.actions.client",
                "tag": "reload",
            },
        },
    }
