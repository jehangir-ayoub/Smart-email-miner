# Smart-Email-Miner
This project is an AI-based resume screening system designed to help HR professionals and recruiters automatically identify the most relevant resumes for a given job description — saving time and reducing manual effort.
 Microsoft Graph Email Webhook Processor with Embedding + Auto-Renew
This project is a FastAPI-based webhook service that:

Subscribes to incoming Outlook/Exchange emails via Microsoft Graph API

Automatically receives and fetches full email content

Extracts & chunks text using BeautifulSoup

Embeds chunks via a transformer model and stores them in FAISS vector DB

Periodically auto-renews subscriptions via MS Graph API

Supports ngrok tunneling for local testing

#⚙ Features
 Auto-listens to new Outlook/Exchange emails

 Chunking + Embedding for semantic search

 Microsoft Graph API secure access

 Auto-renew or recreate webhook subscriptions

☁ Lightweight + Local testing with ngrok

#Getting Started
 1. Clone the repo
2. Install dependencies
. Set up ngrok (for local development)
Download ngrok

#Run it with:
4. Set Environment Variables
Create a .env file in the root:
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
TARGET_USER_ID=your-email-id-or-user-guid
WEBHOOK_CALLBACK_URL=https://your-ngrok-url/email/graph-webhook
#▶️ 5. Run the FastAPI App

uvicorn main:app --reload

# PROJEC STRUCTURE

.
├── main.py                        
├── email_webhook.py              
├── subscription.py               
├── functions/
│   ├── document_chunking.py      
│   ├── embedding_model.py        
│   └── vectorstore.py      
├── vector_stores/email_data/    
├── .env                          
└── requirements.txt
