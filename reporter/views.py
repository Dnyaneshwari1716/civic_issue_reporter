from django.shortcuts import render
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse
import os
import re
import requests
import base64
from datetime import datetime
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from email.message import EmailMessage
import smtplib
from urllib.parse import unquote  # For decoding URL-encoded filenames


def clean_complaint(raw_text, location):
    raw_text = re.split(r'\\*Important Notes:\\*|Important Notes:', raw_text, flags=re.IGNORECASE)[0]
    raw_text = re.sub(r"(?i)^Subject:.*\n", "", raw_text)
    raw_text = re.sub(r"(?i)^To the (Municipal Commissioner|Municipal Corporation).*?\n", "", raw_text)
    raw_text = re.sub(r"(?i)^Pune Municipal Corporation.*\n", "", raw_text)
    raw_text = re.sub(r"(?i)^Pune Water Supply Department.*\n", "", raw_text)
    raw_text = re.sub(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}", "", raw_text)

    today = datetime.now().strftime("%d %B %Y")
    raw_text = raw_text.replace("[Date]", today)
    raw_text = raw_text.replace("[Specific Location]", location)
    raw_text = raw_text.replace("[Specific Location in Ambegaon]", location)
    raw_text = re.sub(r'\[.*?\]', '', raw_text)
    raw_text = re.sub(r"(?i)(Sincerely,)\s*\1", r"\1", raw_text)
    raw_text = re.sub(r'\n{3,}', '\n\n', raw_text)

    return raw_text.strip()


def extract_issue_type_from_text(raw_text):
    text_lower = raw_text.lower()
    if any(k in text_lower for k in ['pothole', 'road', 'street', 'manhole', 'crack', 'hole']):
        return 'road'
    elif any(k in text_lower for k in ['water', 'leak', 'pipe']):
        return 'water'
    elif any(k in text_lower for k in ['garbage', 'trash', 'waste', 'dump']):
        return 'garbage'
    elif any(k in text_lower for k in ['electric', 'light', 'power', 'lamp', 'bulb']):
        return 'electricity'
    else:
        return 'general'


def call_gemini_vision_api(image_path, location):
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    with open(image_path, "rb") as img_file:
        image_data = base64.b64encode(img_file.read()).decode('utf-8')

    payload = {
        "contents": [{
            "parts": [
                {
                    "text": f"""
You are an assistant that writes formal civic complaint letters based on images of issues.

Generate ONLY the body of the letter in professional tone. Do NOT include date, subject line, or header — those are added separately.

Make it complaint-specific, based on the issue in the image, and include references to location: {location}.
Do not add duplicate content or repeated greetings or signature lines.
Make the complaint realistic and relevant from a citizen's perspective.
"""
                },
                {"inline_data": {"mime_type": "image/jpeg", "data": image_data}}
            ]
        }]
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.GEMINI_API_KEY
    }

    response = requests.post(endpoint, json=payload, headers=headers)
    if response.status_code == 200:
        try:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            print(f"Error parsing response: {e}")
            return "Could not analyze the image properly and generate complaint."
    else:
        print(f"Gemini API Error: {response.status_code} - {response.text}")
        return "Failed to call Gemini API."


def get_authority_by_issue(issue_type):
    authorities = {
        'road': 'Pune Municipal Corporation',
        'water': 'Pune Water Supply Department',
        'garbage': 'Pune Municipal Corporation - Waste Management',
        'electricity': 'Maharashtra State Electricity Distribution Company',
        'general': 'Pune Municipal Corporation'
    }
    return authorities.get(issue_type.lower(), 'Concerned Authority')


def upload_issue(request):
    if request.method == 'POST':
        mode = request.POST.get('mode')
        if mode == 'capture':
            captured_image = request.POST.get('captured_image')
            if captured_image:
                format, imgstr = captured_image.split(';base64,')
                img_data = base64.b64decode(imgstr)
                img_name = f"captured_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpeg"
                img_path = os.path.join(settings.MEDIA_ROOT, 'uploads', img_name)
                os.makedirs(os.path.dirname(img_path), exist_ok=True)
                with open(img_path, 'wb') as f:
                    f.write(img_data)
                image_url = settings.MEDIA_URL + 'uploads/' + img_name
            else:
                return render(request, 'reporter/upload.html', {'error': 'No image captured!'})
        else:
            image = request.FILES['image']
            fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'uploads'))
            filename = fs.save(image.name, image)
            image_url = settings.MEDIA_URL + 'uploads/' + filename
            img_path = os.path.join(settings.MEDIA_ROOT, 'uploads', filename)

        location = request.POST.get('location', '')
        raw_complaint_text = call_gemini_vision_api(img_path, location)

        if not raw_complaint_text or "Failed" in raw_complaint_text:
            return render(request, 'reporter/upload.html', {'error': 'Failed to generate complaint. Please try again.'})

        clean_text = clean_complaint(raw_complaint_text, location)
        issue_type = extract_issue_type_from_text(clean_text)
        authority_name = get_authority_by_issue(issue_type)

        request.session['complaint_text'] = clean_text
        request.session['location'] = location
        request.session['issue_type'] = issue_type
        request.session['authority_name'] = authority_name
        request.session['image_url'] = image_url

        return render(request, 'reporter/result.html', {
            'location': location,
            'image_url': image_url,
            'complaint_text': clean_text,
            'authority_name': authority_name
        })

    return render(request, 'reporter/upload.html')


def download_complaint_pdf(request):
    complaint_text = request.session.get('complaint_text', 'No complaint generated.')
    location = request.session.get('location', 'Location not specified.')
    issue_type = request.session.get('issue_type', 'general')
    authority_name = request.session.get('authority_name', 'xyz')

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica", 10)
    textobject = p.beginText(50, 750)

    title = f"Formal Complaint Regarding {issue_type.capitalize()} in {location}"
    textobject.textLine(title)
    textobject.textLine("")

    intro = f"{datetime.now().strftime('%d %B %Y')}\nTo the Concerned Authorities,\n{authority_name},\n{location}"
    for line in intro.split('\n'):
        textobject.textLine(line)
    textobject.textLine("")

    subject = f"Subject: Formal Complaint Regarding {issue_type.capitalize()} in {location}"
    textobject.textLine(subject)
    textobject.textLine("")

    for line in complaint_text.splitlines():
        words = line.split(' ')
        current_line = ""
        for word in words:
            test_line = current_line + " " + word if current_line else word
            if p.stringWidth(test_line, "Helvetica", 10) <= 500:
                current_line = test_line
            else:
                textobject.textLine(current_line)
                current_line = word
        if current_line:
            textobject.textLine(current_line)

    textobject.textLine("")
    textobject.textLine("Sincerely,")
    textobject.textLine("Your Name")

    p.drawText(textobject)
    p.showPage()
    p.save()
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/pdf', headers={
        'Content-Disposition': 'attachment; filename="complaint.pdf"',
    })


@csrf_exempt
def send_email_to_authority(request):
    if request.method == 'POST':
        location = request.POST.get('location') or request.session.get('location') or "your area"
        issue_type = request.POST.get('issue_type') or request.session.get('issue_type') or "issue"
        authority_name = request.POST.get('authority_name') or request.session.get('authority_name') or "Concerned Department"
        complaint_text = request.session.get('complaint_text', 'Complaint text not available.')

        user_email = settings.EMAIL_HOST_USER
        user_name = "Dnyaneshwari Jadhawar"
        app_password = os.getenv('EMAIL_HOST_PASSWORD')
        receiver_email = "jadhawardnyaneshwari@gmail.com"

        subject = f"Complaint Regarding {issue_type.capitalize()} in {location}"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{user_name} <{user_email}>"
        msg["To"] = receiver_email
        msg.set_content(f"""To: {authority_name}
Location: {location}

{complaint_text}

Sincerely,
{user_name}
""")

        try:
            image_url = request.POST.get('image_url') or request.session.get('image_url')
            if image_url:
                relative_path = unquote(image_url.replace(settings.MEDIA_URL, ''))
                image_path = os.path.join(settings.MEDIA_ROOT, relative_path)
                with open(image_path, 'rb') as f:
                    img_data = f.read()
                    img_name = os.path.basename(image_path)
                    msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename=img_name)
        except Exception as e:
            print(f"Image attachment failed: {e}")

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(user_email, app_password)
                smtp.send_message(msg)
            messages.success(request, "✅ Complaint sent to the authority via email with image.")
        except Exception as e:
            messages.error(request, f"❌ Failed to send email: {e}")

        return render(request, 'reporter/result.html', {
    'location': location,
    'issue_type': issue_type,
    'authority_name': authority_name,
    'complaint_text': complaint_text,
    'image_url': request.session.get('image_url', '')
})
      
    return HttpResponse("Invalid request method", status=405)


# from django.shortcuts import render, redirect
# from django.contrib.auth import authenticate, login, logout
# from django.contrib import messages
# from .forms import UserRegisterForm
# from .models import UserProfile, Complaint
# from django.contrib.auth.decorators import login_required

# def register_view(request):
#     if request.method == 'POST':
#         form = UserRegisterForm(request.POST)
#         if form.is_valid():
#             user = form.save()
#             user_type = form.cleaned_data.get('user_type')
#             UserProfile.objects.create(user=user, user_type=user_type)
#             messages.success(request, "Account created successfully!")
#             return redirect('login')
#     else:
#         form = UserRegisterForm()
#     return render(request, 'reporter/register.html', {'form': form})

# def login_view(request):
#     if request.method == 'POST':
#         username = request.POST['username']
#         password = request.POST['password']
#         user = authenticate(request, username=username, password=password)
#         if user is not None:
#             login(request, user)
#             profile = UserProfile.objects.get(user=user)
#             if profile.user_type == 'authority':
#                 return redirect('authority_dashboard')
#             else:
#                 return redirect('user_dashboard')
#         else:
#             messages.error(request, "Invalid username or password.")
#     return render(request, 'reporter/login.html')

# @login_required
# def logout_view(request):
#     logout(request)
#     return redirect('login')

# @login_required
# def user_dashboard(request):
#     complaints = Complaint.objects.filter(user=request.user)
#     return render(request, 'reporter/user_dashboard.html', {'complaints': complaints})

# @login_required
# def authority_dashboard(request):
#     complaints = Complaint.objects.all()
#     return render(request, 'reporter/authority_dashboard.html', {'complaints': complaints})


# from django.shortcuts import render, redirect
# from django.conf import settings
# from django.core.files.storage import FileSystemStorage
# from django.http import HttpResponse
# from django.contrib import messages
# from django.contrib.auth.decorators import login_required
# from django.utils import timezone
# from .models import Complaint, Department
# from .email_tools import send_complaint_email
# import os
# import re
# import requests
# import base64
# from datetime import datetime
# from io import BytesIO
# from reportlab.pdfgen import canvas
# from reportlab.lib.pagesizes import letter
# # Add these functions to views.py (before the upload_issue view)

# def call_gemini_vision_api(image_path, location):
#     """Call Gemini API to analyze image and generate complaint text"""
#     try:
#         endpoint = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent"
#         with open(image_path, "rb") as img_file:
#             image_data = base64.b64encode(img_file.read()).decode('utf-8')

#         payload = {
#             "contents": [{
#                 "parts": [
#                     {
#                         "text": f"""
# Generate a formal civic complaint based on this image showing an issue at {location}.
# Include:
# 1. Clear description of the issue
# 2. Specific location details
# 3. Request for resolution
# 4. Professional tone
# """
#                     },
#                     {"inline_data": {"mime_type": "image/jpeg", "data": image_data}}
#                 ]
#             }]
#         }

#         headers = {
#             "Content-Type": "application/json",
#             "x-goog-api-key": settings.GEMINI_API_KEY
#         }

#         response = requests.post(endpoint, json=payload, headers=headers)
#         response.raise_for_status()  # Raises exception for 4XX/5XX errors
        
#         return response.json()['candidates'][0]['content']['parts'][0]['text']
    
#     except Exception as e:
#         print(f"Gemini API Error: {str(e)}")
#         return f"Standard complaint about issue at {location}. Please add details."

# def clean_complaint(raw_text, location):
#     """Clean and format the generated complaint text"""
#     if not raw_text:
#         return f"Formal complaint regarding an issue at {location}"
    
#     # Remove duplicate headers/footers
#     clean_text = re.sub(r'(Dear|To|Subject|Sincerely).*?\n', '', raw_text, flags=re.IGNORECASE)
#     clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)  # Remove extra newlines
#     clean_text = clean_text.replace("[Location]", location)
    
#     return clean_text.strip()

# def extract_issue_type_from_text(text):
#     """Determine issue type from complaint text"""
#     text_lower = text.lower()
#     if any(kw in text_lower for kw in ['pothole', 'road', 'street']):
#         return 'Road Damage'
#     elif any(kw in text_lower for kw in ['garbage', 'waste', 'trash']):
#         return 'Sanitation'
#     elif any(kw in text_lower for kw in ['water', 'leak', 'pipe']):
#         return 'Water Supply'
#     elif any(kw in text_lower for kw in ['light', 'lamp', 'electric']):
#         return 'Electricity'
#     return 'General Complaint'

# def upload_issue(request):
#     if request.method == 'POST':
#         # Handle image capture/upload
#         if request.POST.get('mode') == 'capture':
#             captured_image = request.POST.get('captured_image')
#             if captured_image:
#                 format, imgstr = captured_image.split(';base64,')
#                 img_data = base64.b64decode(imgstr)
#                 img_name = f"captured_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpeg"
#                 img_path = os.path.join(settings.MEDIA_ROOT, 'uploads', img_name)
#                 os.makedirs(os.path.dirname(img_path), exist_ok=True)
#                 with open(img_path, 'wb') as f:
#                     f.write(img_data)
#                 image_url = settings.MEDIA_URL + 'uploads/' + img_name
#         else:
#             image = request.FILES['image']
#             fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'uploads'))
#             filename = fs.save(image.name, image)
#             image_url = settings.MEDIA_URL + 'uploads/' + filename
#             img_path = os.path.join(settings.MEDIA_ROOT, 'uploads', filename)

#         location = request.POST.get('location', '')
        
#         # Generate complaint text (your existing Gemini integration)
#         raw_complaint_text = call_gemini_vision_api(img_path, location)
#         clean_text = clean_complaint(raw_complaint_text, location)
#         issue_type = extract_issue_type_from_text(clean_text)
        
#         # Auto-assign department
#         department = Department.objects.filter(
#             issue_types__icontains=issue_type
#         ).first()
        
#         # Save complaint
#         complaint = Complaint.objects.create(
#             user=request.user if request.user.is_authenticated else None,
#             image=image_url,
#             issue_type=issue_type,
#             description=clean_text,
#             location=location,
#             department=department,
#             status='Pending'
#         )
        
#         # Send email
#         if department and department.email:
#             send_complaint_email(complaint)
        
#         return render(request, 'reporter/result.html', {
#             'complaint': complaint,
#             'image_url': image_url
#         })
    
#     return render(request, 'reporter/upload.html')

# @login_required
# def update_status(request, complaint_id):
#     if request.method == 'POST':
#         complaint = Complaint.objects.get(id=complaint_id)
#         complaint.status = request.POST.get('status')
#         complaint.save()
#         messages.success(request, "Status updated successfully!")
#     return redirect('authority_dashboard')

# # reporter/views.py
# from django.shortcuts import render, redirect
# from django.http import HttpResponse
# from django.conf import settings
# from io import BytesIO
# from reportlab.pdfgen import canvas
# from reportlab.lib.pagesizes import letter
# from .models import Complaint
# import os
# from django.contrib import messages

# def download_complaint_pdf(request):
#     """Generate PDF from complaint data"""
#     try:
#         complaint_id = request.GET.get('id')
#         if not complaint_id:
#             return HttpResponse("Missing complaint ID", status=400)
            
#         complaint = Complaint.objects.get(id=complaint_id)
        
#         # Create PDF
#         buffer = BytesIO()
#         p = canvas.Canvas(buffer, pagesize=letter)
        
#         # Add content
#         p.drawString(100, 750, f"Complaint ID: {complaint.id}")
#         p.drawString(100, 730, f"Issue Type: {complaint.issue_type}")
#         p.drawString(100, 710, f"Location: {complaint.location}")
        
#         # Add complaint text with proper wrapping
#         text = p.beginText(100, 690)
#         text.setFont("Helvetica", 12)
        
#         for line in complaint.description.split('\n'):
#             text.textLine(line)
            
#         p.drawText(text)
#         p.showPage()
#         p.save()
        
#         # Get PDF value and return response
#         buffer.seek(0)
#         return HttpResponse(buffer, content_type='application/pdf')
        
#     except Complaint.DoesNotExist:
#         return HttpResponse("Complaint not found", status=404)
#     except Exception as e:
#         return HttpResponse(f"Error generating PDF: {str(e)}", status=500)