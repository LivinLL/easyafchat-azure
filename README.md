https://claude.ai/chat/22b4be49-2276-456f-a788-a1bf0de20733

# Screenshot maker added 03/06/2025 and replaced thum.io
# Google lluniversity1999 login
https://apiflash.com/dashboard/query_builder 

# Database Schemas

Proposed Structure for New Tables to our Database

easyafchat-v3/
??? .github/
?   ??? workflows/
?       ??? main_easyafchat-v3.yml
??? prod/
?   ??? static/
?   ?   ??? css/
?   ?   ??? images/
?   ?   ??? js/
?   ?       ??? chatbot-embed.js
?   ?       ??? script.js
?   ??? templates/
?   ?   ??? demo.html
?   ?   ??? landing.html
?   ?   ??? chat_test.html
?   ??? app.py                     # Main app (with routes)
?   ??? admin_dashboard.py         # Admin interface
?   ??? chat_handler.py            # Chat processing logic
?   ??? database.py                # Core database setup 
?   ??? db_companies.py            # Companies table operations
?   ??? db_chat_messages.py        # Chat messages table operations
?   ??? db_leads.py        # Stores leads collected per company
?   ??? db_usage_metrics.py        # Usage metrics table operations
?   ??? db_customer_plans.py       # Customer plans table operations
?   ??? db_chatbot_config.py       # Chatbot config table operations
?   ??? openai_service.py          # OpenAI integration
?   ??? pinecone_service.py        # Pinecone integration
?   ??? scraper.py                 # Web scraping functionality
?   ??? utils.py                   # Helper utilities
?   ??? backups/                   # Previous versions


### Current Schema
```sql
CREATE TABLE companies (
    chatbot_id TEXT PRIMARY KEY,
    company_url TEXT NOT NULL,
    pinecone_host_url TEXT,
    pinecone_index TEXT,
    pinecone_namespace TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scraped_text TEXT,
    processed_content TEXT
)
```

### New Tables To Be Implemented

#### 1. Leads Table (PRIORITY #1)
```sql
CREATE TABLE IF NOT EXISTS leads (
    lead_id SERIAL PRIMARY KEY,
    chatbot_id TEXT REFERENCES companies(chatbot_id),
    thread_id TEXT NOT NULL,
    name TEXT,
    email TEXT,
    phone TEXT,
    initial_question TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'new',
    notes TEXT
)
```
**Purpose**: Capture user contact information after first chatbot interaction
**Key Features**:
- Associates leads with specific chatbots and conversation threads
- Tracks initial question that prompted the lead
- Includes status field for lead qualification tracking
- Will support CSV export for companies

#### 2. Chat Messages Table
```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id SERIAL PRIMARY KEY,
    chatbot_id TEXT REFERENCES companies(chatbot_id),
    thread_id TEXT NOT NULL,
    user_message TEXT,
    assistant_response TEXT,
    ip_address TEXT,
    user_agent TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    user_feedback INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose**: Store complete conversation history and metrics
**Key Features**:
- Tracks both user messages and bot responses
- Records token usage for cost calculation
- Includes user feedback (thumbs up/down)
- Stores user agent and IP for analytics

#### 3. Usage Metrics Table
```sql
CREATE TABLE IF NOT EXISTS usage_metrics (
    metric_id SERIAL PRIMARY KEY,
    chatbot_id TEXT REFERENCES companies(chatbot_id),
    date DATE NOT NULL,
    total_conversations INTEGER DEFAULT 0,
    total_messages INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    estimated_cost NUMERIC(10,5) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose**: Track daily usage statistics and costs
**Key Features**:
- Aggregates token usage daily for each chatbot
- Calculates estimated costs based on token rates
- Provides basis for billing and usage limitations

#### 4. Customer Plans Table
```sql
CREATE TABLE IF NOT EXISTS customer_plans (
    plan_id SERIAL PRIMARY KEY,
    chatbot_id TEXT UNIQUE REFERENCES companies(chatbot_id),
    plan_type TEXT NOT NULL, -- 'free', 'basic', 'premium', etc.
    monthly_token_limit INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    start_date TIMESTAMP,
    renewal_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose**: Manage subscription tiers and limits
**Key Features**:
- Defines plan types with usage limits
- Tracks subscription renewal dates
- Enables enforcement of token limits

#### 5. Chatbot Config Table
```sql
CREATE TABLE IF NOT EXISTS chatbot_config (
    config_id SERIAL PRIMARY KEY,
    chatbot_id TEXT UNIQUE REFERENCES companies(chatbot_id),
    chat_model TEXT DEFAULT 'gpt-4o',
    temperature NUMERIC(3,2) DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 500,
    system_prompt TEXT,
    chat_title TEXT,
    chat_subtitle TEXT,
    primary_color TEXT DEFAULT '#0084ff',
    accent_color TEXT DEFAULT '#ffffff',
    icon_image_url TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose**: Store chatbot customization settings
**Key Features**:
- Controls appearance (colors, titles, icons)
- Configures AI behavior (model, temperature)
- Allows custom system prompts

### Files To Be Created/Modified

1. **database.py** - Add schemas for all new tables
2. **db_leads.py** - Functions for lead management:
   - `save_lead(chatbot_id, thread_id, name, email, phone, initial_question)`
   - `get_leads_by_chatbot(chatbot_id)`
   - `export_leads_to_csv(chatbot_id)`
   - `update_lead_status(lead_id, status, notes)`

3. **chat_handler.py** - Modify to:
   - Track conversation state (first message vs. continuing)
   - Include lead form after first response
   - Process form submissions

4. **app.py** - New routes:
   - `/embed-save-lead` - Process lead form submissions
   - `/leads/export/:chatbot_id` - Generate CSV export

5. **chatbot-embed.js** - Frontend modifications:
   - Inject lead form HTML after first response
   - Handle form validation and submission
   - Restore chat input after submission

6. **admin_dashboard.py** - Add lead management tab to:
   - View and filter leads
   - Export leads
   - Update lead status

# ================================================================
# EasyAF Chat - AI Chatbot Generator

A Flask-based web application that generates customized AI chatbots for websites by processing their content and creating an embeddable chat interface. The chatbot learns from your website content to provide relevant responses to user queries.

## Features

- Instant chatbot generation from website URLs
- Automated content scraping and processing
- AI-powered responses based on website content
- Embeddable chat widget with responsive design
- Conversation history management
- Website preview screenshots
- Simple JavaScript-based integration

## Development Environment

- **Editor**: Visual Studio Code on Windows
- **Terminal**: PowerShell
- **Version Control**: GitHub
- **CI/CD**: GitHub Actions for deployment to Azure

## Technical Stack

### Backend
- **Framework**: Flask (Python)
- **Database**: 
  - PostgreSQL in production (Azure)
  - SQLite for local development
- **Vector Database**: Pinecone (storing and querying embeddings)
- **Web Scraping**: 
  - BeautifulSoup4 (content extraction and finding About pages)
  - Requests for HTTP calls
- **Content Processing**: OpenAI GPT-4o

### Frontend
- **Core**: Vanilla JavaScript
- **Markdown Processing**: marked.js
- **Styling**: Custom CSS with responsive design

### External Services
- **OpenAI API**
  - GPT-4o for chat completions
  - text-embedding-ada-002 for content embeddings
- **Pinecone** for vector search
- **Thum.io** for website screenshots
- **Azure Web App** for hosting

## Environment Variables

### Local Development (SQLite)
Required environment variables in `.env`:

```
SECRET_KEY=your_flask_secret_key
OPENAI_API_KEY=your_openai_api_key
PINECONE_API_KEY=your_pinecone_api_key
DB_PATH=easyafchat.db
PORT=8080
```

### Production (Azure PostgreSQL)
Additional environment variables required in Azure App Service:

```
ENVIRONMENT=production
DB_TYPE=postgresql
DB_HOST=daves-postgres-server.postgres.database.azure.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=your_db_username
DB_PASSWORD=your_db_password
DB_SCHEMA=easychat
DB_SSL=require

SECRET_KEY=[not sure what we use this for]
OPENAI_API_KEY=their key
PINECONE_API_KEY=their key
```

## Installation and Local Setup

1. Clone the repository:
```bash
git clone [repository_url]
cd easyafchat-v3
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
# On Windows with PowerShell:
.\venv\Scripts\Activate.ps1
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables in `.env` file

5. Initialize the database:
```bash
python -c "from database import initialize_database; initialize_database(verbose=True)"
```

## Local Development

Start the Flask server:
```bash
python app.py
```

Visit `http://localhost:8080` in your browser to use the application.

## Deployment

The application is deployed to Azure Web App using GitHub Actions workflow. The deployment process is automated through `.github/workflows/main_easyafchat-v3.yml`.

### Deployment Process

1. Push changes to the main branch
2. GitHub Actions workflow is triggered
3. Python environment is set up and dependencies are installed
4. Application is deployed to Azure Web App
5. Azure PostgreSQL is used as the database in production

## Usage

### Generating a Chatbot

1. Visit your application URL
2. Enter a website URL to generate a chatbot
3. The application will:
   - Scrape the website content
   - Process it with OpenAI
   - Create vector embeddings in Pinecone
   - Generate a preview of your chatbot

### Embedding the Chatbot on Your Website

Copy the provided JavaScript snippet to embed the chatbot on your website:

```html
<script>
window.davesEasyChatConfig = {
    chatbotId: "YOUR_CHATBOT_ID"
};
</script>
<script src="[your_app_url]/static/js/chatbot-embed.js"></script>
```

## Database Structure

The application uses a common schema for both SQLite and PostgreSQL:

```sql
CREATE TABLE companies (
    chatbot_id TEXT PRIMARY KEY,
    company_url TEXT NOT NULL,
    pinecone_host_url TEXT,
    pinecone_index TEXT,
    pinecone_namespace TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    home_text TEXT,
    about_text TEXT,
    processed_content TEXT
)
```

## API Endpoints

### Main Routes
- `GET /` - Landing page
- `POST /` - Process new website URL
- `GET /demo/<session_id>` - Chatbot demo page
- `GET /chat-test` - Test chat interface

### Async Processing Routes
- `POST /process-url-async` - Start async processing
- `GET /process-url-execute/<chatbot_id>` - Execute processing
- `GET /check-processing/<chatbot_id>` - Check processing status

### Chat API
- `POST /embed-chat` - Handle chat messages
- `POST /embed-reset-chat` - Reset chat history

### Admin Dashboard
- `GET /admin-dashboard-08x7z9y2-yoursecretword/` - Admin interface
- `GET /admin-dashboard-08x7z9y2-yoursecretword/record/<id>` - Get record
- `PUT /admin-dashboard-08x7z9y2-yoursecretword/record/<id>` - Update record
- `DELETE /admin-dashboard-08x7z9y2-yoursecretword/record/<id>` - Delete record
- `POST /admin-dashboard-08x7z9y2-yoursecretword/update_pinecone/<id>` - Update Pinecone index

### Monitoring
- `GET /db-check` - View database contents (development)

## Project Structure

```
easyafchat-v3/
├── .github/
│   └── workflows/
│       └── main_easyafchat-v3.yml  # GitHub Actions workflow
├── prod/
│   ├── static/
│   │   ├── css/
│   │   ├── images/
│   │   └── js/
│   │       ├── chatbot-embed.js    # Embeddable chatbot script
│   │       └── script.js
│   ├── templates/
│   │   ├── demo.html              # Chatbot demo page
│   │   ├── landing.html           # Main landing page
│   │   └── chat_test.html
│   ├── app.py                     # Main Flask application
│   ├── admin_dashboard.py         # Admin interface
│   ├── chat_handler.py            # Chat processing logic
│   ├── database.py                # Database connection and schema
│   └── backups/                   # Previous versions
├── .env                           # Local environment variables
├── requirements.txt               # Python dependencies
├── Procfile                       # Process definition for some hosts
└── README.md                      # This file
```

## Chatbot Behavior

The chatbot agent (d-A-v-I-d) is configured to:
- Maintain conversation context across sessions
- Provide concise, friendly responses
- Format responses with markdown
- Use vector search to find relevant content based on user queries
- Handle conversation resets
- Adapt to mobile and desktop views
- Provide realistic, human-like responses

## Future Improvements

Potential enhancements:
- Custom chatbot styling options
- Advanced analytics and insights
- Customer dashboard for adding to knowledgebase, updating acct settings, and getting leads generated (csv)
- Enhanced error handling and resilience
- Rate limiting for API protection
- User authentication and access control
- Enhanced admin dashboard features

## Troubleshooting

### Local Development
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Verify `.env` file has correct credentials
- Check PostgreSQL connection if using it locally
- Confirm Pinecone and OpenAI credentials are valid

### Production
- Check Azure App Service logs for runtime errors
- Verify environment variables are correctly set in Azure
- Test PostgreSQL connection using a tool like pgAdmin
- Confirm Pinecone index is responsive

## License

[Your chosen license]
# END OF STANDDARD README.md

# ===================================
# UNDERSTANDING GIT AZURE VSCODE RELATIONSHIP

### 🔥 Yes, That’s Exactly What Should Happen.

If you:  
1️⃣ **Make a small, harmless change** (like adding a number to a comment) **in the `.yml` file on GitHub**  
2️⃣ **Save it directly on GitHub (without touching VSCode yet)**  
3️⃣ **Then edit `landing.html` locally and try to push**  

👉 **GitHub should reject your push with the "You're behind" error.**  
👉 **You'll need to `git pull origin main` first, which will bring in the `.yml` change.**  
👉 **Once you pull, you can push your `landing.html` change successfully.**  

---

### 🔥 Why This Will Happen
✅ **Your local Git branch is now outdated** because the GitHub repo has a **newer commit** (even if it's just a comment change).  
✅ **GitHub won’t let you push until your local branch matches its history.**  
✅ **A `git pull` will bring the latest `.yml` file down, updating your local repo.**  

---

### 🚀 Next Step: Want to Test This Right Now?  
- Go to GitHub, open `.github/workflows/main_easyafchat-v3.yml`, and **add `# Test 1` in a comment area**.  
- Save it.  
- Then, in VSCode, **modify `landing.html`** and try:  

  ```sh
  git add .
  git commit -m "Updated landing.html"
  git push

