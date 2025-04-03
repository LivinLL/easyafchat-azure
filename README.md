# GoEasyChat - AI Chatbot Generator by David Greenwalt

A powerful Flask-based web application that generates customized AI chatbots for websites by processing their content and creating an embeddable chat interface. Create a smart AI-powered chatbot for your website in less than 60 seconds!

## Features

- **Instant Chatbot Generation**: Create a chatbot from any website URL in under 60 seconds
- **Smart AI-Powered Responses**: Leverages OpenAI's GPT-4o for intelligent, context-aware conversations
- **Automated Content Processing**: Scrapes website content to build a knowledge base
- **Embeddable Chat Widget**: Responsive design that works on any device
- **Lead Generation**: Built-in lead capture form to collect visitor information
- **Google & Microsoft Authentication**: Secure sign-in options
- **User Dashboard**: Manage chatbots, view leads, and customize settings
- **Knowledge Base Enhancement**: Upload additional documents to make your chatbot smarter
- **Conversation History**: Track and analyze chat interactions
- **Website Preview**: See how your chatbot looks with your website
- **Simple Integration**: Add your chatbot with a simple JavaScript snippet

## User Flow

1. **Creation**: Users enter their website URL on our landing page
2. **Processing**: We scrape their website content, analyze it with AI, and create embeddings
3. **Demo**: Users see a preview of their chatbot with their website
4. **Claiming**: Users can claim their chatbot by signing in with Google or Microsoft
5. **Dashboard**: Access features like playground testing, embedding code, and lead management
6. **Deployment**: Add the chatbot to their website with a simple code snippet

## Development Environment

- **Editor**: Visual Studio Code on Windows
- **Terminal**: PowerShell
- **Version Control**: GitHub
- **CI/CD**: GitHub Actions for deployment to Azure

## Technical Stack

### Backend
- **Framework**: Flask (Python 3)
- **Database**: 
  - PostgreSQL in production (Azure)
  - SQLite for local development
- **Vector Database**: Pinecone (storing and querying embeddings)
- **Web Scraping**: 
  - BeautifulSoup4 (content extraction)
  - Requests for HTTP calls
- **Content Processing**: OpenAI GPT-4o
- **Authentication**: Google & Microsoft OAuth integration

### Frontend
- **Core**: Vanilla JavaScript
- **Markdown Processing**: marked.js
- **Styling**: Custom CSS with responsive design

### External Services
- **OpenAI API**
  - GPT-4o for chat completions
  - text-embedding-ada-002 for content embeddings
- **Pinecone** for vector search
- **APIFlash** for website screenshots
- **Azure Web App** for hosting
- **Google & Microsoft OAuth** for authentication

## Security Features

- **reCAPTCHA v3**: Bot protection for forms
- **Rate Limiting**: Prevents abuse of endpoints
- **CSRF Protection**: Cross-site request forgery prevention
- **Input Validation**: Sanitized inputs to prevent attacks
- **Secure Authentication**: OAuth with Google and Microsoft
- **Honeypot Fields**: Additional bot detection
- **HTTPS Enforcement**: Secure communication

## Database Structure

The application uses PostgreSQL in production and SQLite for development with the following core tables:

### Companies Table
Stores information about created chatbots and their associated websites.

### Chatbot Config Table
Stores customization settings for individual chatbots.

### Leads Table
Captures user contact information collected through the chatbot.

### Documents Table
Stores additional knowledge documents uploaded by users.

### Users Table
Manages user accounts and authentication details.

## Key Components

### Chat Handler
Manages conversation state, context, and interactions with the OpenAI API.

### Vector Cache
In-memory cache for vector embeddings to improve performance.

### Document Processing
Handles the extraction and embedding of document content.

### Admin Dashboard
Interface for system administration and monitoring.

## API Endpoints

### Main Routes
- **Landing Page**: User entry point to create chatbots
- **Demo**: Demonstrates the created chatbot
- **Dashboard**: User interface for managing chatbots

### Chat API
- **Embed Chat**: Handles chat messages from embedded chatbots
- **Lead Submission**: Processes lead form submissions

### Document Management
- **Upload Document**: Adds content to a chatbot's knowledge base
- **Document Processing**: Converts documents into vector embeddings

## Project Structure

The application follows a modular structure to separate concerns:

```
goeasychat/
├── .github/workflows/    # CI/CD configuration
├── prod/
│   ├── static/           # Static assets (CSS, JS, images)
│   ├── templates/        # HTML templates
│   ├── app.py            # Main application entry point
│   ├── chat_handler.py   # Chat processing logic
│   ├── database.py       # Database connection and schema
│   ├── db_leads.py       # Leads management
│   └── documents_blueprint.py  # Document handling
├── .env                  # Local environment variables
└── requirements.txt      # Python dependencies
```

## Future Enhancements

- **Custom Avatar Selection**: Personalize chatbot appearance
- **Welcome Message Customization**: Set custom greeting messages
- **Advanced Analytics**: Track chatbot performance and user engagement
- **Multi-language Support**: Expand to additional languages
- **Integration API**: Connect with CRM and marketing tools
- **Advanced Chatbot Logic**: Custom workflows and decision trees

## Google Privacy and Terms of Service
https://policies.google.com/privacy
https://policies.google.com/terms
