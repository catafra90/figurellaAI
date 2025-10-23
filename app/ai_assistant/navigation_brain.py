# app/ai/brains/navigation_brain.py

def navigate_to(page):
    page = page.lower()
    if "home" in page:
        return {"redirect": "/"}
    elif "daily" in page or "check-in" in page:
        return {"redirect": "/report"}
    elif "report" in page:
        return {"redirect": "/reports"}
    elif "client" in page:
        return {"redirect": "/clients"}
    else:
        return {"message": "Sorry, I didn't understand the destination."}
