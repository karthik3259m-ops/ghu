import os
import random
import subprocess
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

def commit_batch():
    print("\n--- Syncing with GitHub ---")
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
    subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", "downloads/*"], check=False)
    subprocess.run("git commit -m 'Auto-uploading new papers' || exit 0", shell=True, check=False)
    
    # Push changes back to origin
    result = subprocess.run(["git", "push"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠️ Git push failed or nothing to push: {result.stderr}")

def scrape():
    download_dir = "downloads"
    os.makedirs(download_dir, exist_ok=True)

    with sync_playwright() as p:
        # Pass chrome flags to decrease detection footprint
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            locale="en-US"
        )
        
        page = context.new_page()
        
        # Apply stealth patches
        try:
            stealth_sync(page)
        except Exception as e:
            print(f"⚠️ Stealth initialization warning: {e}")

        base_url = "https://www.brigadegroup.com/"

        for pg_num in range(1, 4):
            target = f"{base_url}page/{pg_num}/"
            print(f"🔎 Visiting Page {pg_num}...")
            
            try:
                page.goto(target, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(random.randint(5000, 8000))

                # Extract article links
                articles = page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a'))
                        .map(a => a.href)
                        .filter(href => href.includes('/jobs/') && !href.includes('.pdf') && !href.includes('category'));
                }''')

                for art_url in set(articles):
                    print(f"  🔗 Checking article: {art_url}")
                    try:
                        page.goto(art_url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(2000)

                        # Find PDF links
                        pdfs = page.evaluate('''() => {
                            return Array.from(document.querySelectorAll('a'))
                                .map(a => a.href)
                                .filter(href => href.toLowerCase().endsWith('.pdf'));
                        }''')

                        for pdf_url in set(pdfs):
                            fname = pdf_url.split('/')[-1].split('?')[0]
                            file_path = os.path.join(download_dir, fname)

                            if not os.path.exists(file_path):
                                print(f"    📥 Downloading: {fname}")
                                
                                # Fetch PDF using Playwright's authenticated request context
                                response = context.request.get(pdf_url)
                                
                                if response.status == 200:
                                    body = response.body()
                                    
                                    # Verify it's actually a PDF (PDF files start with %PDF)
                                    if body.startswith(b'%PDF'):
                                        with open(file_path, 'wb') as f:
                                            f.write(body)
                                        print(f"    ✅ Saved: {fname}")
                                    else:
                                        print(f"    ⚠️ Warning: Downloaded file is not a valid PDF: {fname}")
                                else:
                                    print(f"    ❌ Download failed with status {response.status}")
                                    
                                page.wait_for_timeout(1000)

                    except Exception as e:
                        print(f"    ❌ Error scraping article {art_url}: {e}")
                        continue

            except Exception as e:
                print(f"❌ Error on main page {pg_num}: {e}")
                continue

        browser.close()
    
    commit_batch()

if __name__ == "__main__":
    scrape()
