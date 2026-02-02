from pyngrok import ngrok
import time

# Open a tunnel to your running server (Port 5000)
public_url = ngrok.connect(5000).public_url

print("📢 YOUR APP IS LIVE ON THE INTERNET!")
print("--------------------------------------------------")
print(f"👉 OPEN THIS ON YOUR PHONE: {public_url}")
print("--------------------------------------------------")

# Keep it alive
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping...")