import streamlit as st
from email_validator import validate_email, EmailNotValidError
import dns.resolver
import smtplib
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# Function to check email validity
def validate_email_address(email, blacklist, disposable_providers, custom_sender="test@example.com", max_retries=3):
    """Enhanced email validation with DNS, SMTP, and blacklist checks."""
    retries = 0
    
    # Step 1: Syntax validation
    try:
        validate_email(email)
    except EmailNotValidError as e:
        return email, "Invalid", f"Invalid syntax: {str(e)}"
    
    domain = email.split("@")[-1]

    # Step 2: Blacklist check
    if domain in blacklist:
        return email, "Blacklisted", "Domain is blacklisted."

    # Step 3: Disposable email provider check
    if domain in disposable_providers:
        return email, "Disposable", "Domain is a disposable email provider."

    # Step 4: DNS Validation
    while retries < max_retries:
        try:
            mx_records = dns.resolver.resolve(domain, "MX")
            if not mx_records:
                return email, "Invalid", "No MX records found for domain."
            
            # Sort MX records by priority (lowest priority number is best)
            mx_records.sort(key=lambda r: r.preference)
            mx_host = str(mx_records[0].exchange).rstrip(".")
            return email, "Valid", f"MX records found, prioritized at {mx_host}"
        except dns.resolver.NXDOMAIN:
            return email, "Invalid", "Domain does not exist."
        except dns.resolver.Timeout:
            retries += 1
            time.sleep(1)  # Sleep before retrying
        except Exception as e:
            return email, "Invalid", f"DNS error: {str(e)}"
    
    return email, "Invalid", "DNS query failed after multiple retries."

# Function to perform SMTP check (this is done only if DNS and blacklist checks are passed)
def smtp_check(email, mx_host, custom_sender="test@example.com"):
    """Performs the SMTP check on a given email."""
    try:
        smtp = smtplib.SMTP(mx_host, timeout=10)
        smtp.helo()
        smtp.mail(custom_sender)
        code, _ = smtp.rcpt(email)
        smtp.quit()
        if code == 250:
            return "Valid", "Email exists and is reachable."
        elif code == 550:
            return "Invalid", "Mailbox does not exist."
        elif code == 451:
            return "Greylisted", "Temporary error, try again later."
        else:
            return "Invalid", f"SMTP response code {code}."
    except smtplib.SMTPConnectError:
        return "Invalid", "SMTP connection failed."
    except Exception as e:
        return "Invalid", f"SMTP error: {str(e)}"

# Streamlit App
st.title("Inboxify by EverTech")

# Additional Information
st.write("""
**For Inboxify access, please visit [Amazon Appstore](https://www.amazon.com/gp/product/B0DV3S92JY)**  
This version is created solely for **open source basis**.  
The original application is capable of handling **50,000+ email IDs at once**.
""")

# Blacklist upload
blacklist_file = st.file_uploader("Upload a blacklist file (optional)", type=["txt"])
blacklist = set()
if blacklist_file:
    blacklist = set(line.strip() for line in blacklist_file.read().decode("utf-8").splitlines())
    st.write(f"Loaded {len(blacklist)} blacklisted domains.")

# Disposable email providers list
disposable_providers = {
    "tempmail.com", "mailinator.com", "guerrillamail.com", "10minutemail.com", "throwawaymail.com",
    "temp-mail.org", "discard.email", "emailondeck.com", "maildrop.cc"
}

# File upload
uploaded_file = st.file_uploader("Upload a .txt file with emails", type=["txt"])
if uploaded_file:
    emails = uploaded_file.read().decode("utf-8").splitlines()

    st.write(f"Processing {len(emails)} emails...")

    # Process emails
    results = []
    progress = st.progress(0)

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(validate_email_address, email.strip(), blacklist, disposable_providers) for email in emails if email.strip()]
        for idx, future in enumerate(as_completed(futures)):
            email, status, message = future.result()
            if status == "Valid":
                # Perform SMTP check only for valid emails
                mx_host = message.split(", prioritized at ")[-1] if "MX records found" in message else ""
                if mx_host:
                    smtp_status, smtp_message = smtp_check(email, mx_host)
                    results.append((email, smtp_status, smtp_message))
                else:
                    results.append((email, status, message))
            else:
                results.append((email, status, message))
            
            progress.progress((idx + 1) / len(emails))

    # Display results
    df = pd.DataFrame(results, columns=["Email", "Status", "Message"])
    st.dataframe(df)

    # Summary report
    st.write("### Summary Report")
    st.write(f"Total Emails Processed: {len(emails)}")
    for status in ["Valid", "Invalid", "Greylisted", "Blacklisted", "Disposable"]:
        count = df[df["Status"] == status].shape[0]
        st.write(f"{status} Emails: {count}")

    # Export results
    csv = df.to_csv(index=False)
    st.download_button("Download Results", data=csv, file_name="email_validation_results.csv", mime="text/csv")
