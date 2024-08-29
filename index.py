import streamlit as st
from googleapiclient.discovery import build
import yt_dlp
from pydub import AudioSegment
import os
import tempfile
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

# Load API key and email credentials from .env file
load_dotenv()
api_key = os.getenv('YOUTUBE_API_KEY')
sender_email = os.getenv('SENDER_EMAIL')
email_password = os.getenv('EMAIL_PASSWORD')

# Determine the number of CPU cores available
num_cores = multiprocessing.cpu_count()

# CSS for dark mode and glassmorphism (unchanged)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');

    body {
        font-family: 'Roboto', sans-serif;
        background-color: #1e1e1e;
        color: #e0e0e0;
    }

    .stApp {
        background: rgba( 255, 255, 255, 0.1 );
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 10px;
        padding: 20px;
    }

    .css-1d391kg {
        background-color: transparent !important;
    }

    h1 {
        font-weight: 500;
        color: #ecf0f1;
    }

    h2, h3, h4, h5, h6 {
        font-weight: 400;
        color: #ecf0f1;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Function to get YouTube links (unchanged)
def get_youtube_links(api_key, query, max_results=20):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        search_response = youtube.search().list(
            q=query,
            part='snippet',
            type='video',
            maxResults=max_results
        ).execute()

        videos = []
        for item in search_response['items']:
            video_id = item['id']['videoId']
            video_title = item['snippet']['title']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            videos.append((video_title, video_url))

        return videos
    except Exception as e:
        st.error(f"Failed to fetch YouTube links: {e}")
        return []

# Function to download audio from YouTube (unchanged)
def download_single_audio(url, index, download_path):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{download_path}/song_{index}_%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        downloaded_files = [f for f in os.listdir(download_path) if f.startswith(f"song_{index}_") and f.endswith(".mp3")]
        if downloaded_files:
            return os.path.join(download_path, downloaded_files[0])
        else:
            st.error(f"Downloaded file not found for {url}")
            return None
    except Exception as e:
        st.error(f"Error downloading audio: {e}")
        return None

# Function to download all audio files in parallel (unchanged)
def download_all_audio(video_urls, download_path):
    downloaded_files = []
    progress_bar = st.progress(0)
    num_videos = len(video_urls)
    with ThreadPoolExecutor(max_workers=num_cores) as executor:
        futures = {
            executor.submit(download_single_audio, url, index, download_path): index
            for index, url in enumerate(video_urls, start=1)
        }

        for i, future in enumerate(as_completed(futures)):
            try:
                mp3_file = future.result()
                if mp3_file:
                    downloaded_files.append(mp3_file)
                progress_bar.progress((i + 1) / num_videos)
            except Exception as e:
                st.error(f"Error occurred: {e}")

    return downloaded_files

# Updated function to create a mashup from audio files
def create_mashup(audio_files, output_file, trim_duration):
    mashup = AudioSegment.silent(duration=0)
    for file in audio_files:
        audio = AudioSegment.from_file(file)
        part = audio[:trim_duration * 1000]  # Convert seconds to milliseconds
        mashup += part

    mashup.export(output_file, format="mp3")
    return output_file

# Function to send email with attachment (unchanged)
def send_email(sender_email, receiver_email, subject, body, attachment_path, password):
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        with open(attachment_path, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename= {os.path.basename(attachment_path)}")
            msg.attach(part)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, password)
        text = msg.as_string()
        server.sendmail(sender_email, receiver_email, text)
        server.quit()

        st.success("Email sent successfully!")
    except Exception as e:
        st.error(f"Failed to send email: {e}")

# Main Streamlit app
st.title("YouTube Mashup Creator")

# User inputs
trim_duration = st.number_input("Enter trim duration (seconds)", min_value=1, max_value=60, value=10)
receiver_email = st.text_input("Enter your email address")

# Create and send mashup button
if st.button("Create and Send Mashup"):
    if receiver_email:
        with st.spinner('Creating and sending mashup...'):
            # Get YouTube links
            query = "Sharry Maan"  # Default query, hidden from user
            videos = get_youtube_links(api_key, query, max_results=20)

            if videos:
                # Download audio
                download_path = tempfile.mkdtemp()
                video_urls = [url for _, url in videos]
                audio_files = download_all_audio(video_urls, download_path)

                # Create mashup
                if audio_files:
                    output_file = os.path.join(tempfile.gettempdir(), "mashup.mp3")
                    mashup_file = create_mashup(audio_files, output_file, trim_duration)

                    # Send email
                    subject = "Your YouTube Mashup"
                    body = "Please find attached your custom YouTube mashup."
                    send_email(sender_email, receiver_email, subject, body, mashup_file, email_password)

                    # Cleanup
                    os.remove(mashup_file)
                    for file in audio_files:
                        os.remove(file)
                else:
                    st.error("Failed to download audio files. Please try again.")
            else:
                st.error("No videos found. Please try again later.")
    else:
        st.error("Please enter your email address.")

st.info("This app creates a mashup of Sharry Maan songs and sends it to your email. Just enter the trim duration (how many seconds to use from each song) and your email address, then click the button!")
