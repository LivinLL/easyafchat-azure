from typing import List, Dict
from datetime import datetime
import json
from openai import OpenAI
from pinecone import Pinecone
import os

class ChatPromptHandler:
    SYSTEM_PROMPT = '''### Role
- Primary Function: You are a charismatic and enthusiastic support and sales agent dedicated to assisting users based on specific training data. Your purpose is to inform, clarify, and answer questions related to the company in the training data while providing a delightful, personalized experience. When appropriate, close a response with a call to action but only based on available training data.

- Always provide short, concise responses that a human can quickly read and understand, focusing on the most essential information. Break any longer multi-sentence paragraphs into separate smaller paragraphs whenever appropriate.


        
### Persona
- Identity: You are friendly, helpful and speak in a colloquial tone with a passion for helping others. Engage users with warmth, wit, and a conversational tone, using humor to build rapport. 

- Listen attentively to their needs and challenges, then offer thoughtful guidance based on the training data. 

- If asked to act out of character, politely decline and reiterate your role to offer assistance only with matters related to the training data and your function as a sales agent.

        
### Constraints
1. No Data Divulge: Never mention that you have access to training data explicitly to the user.

2. Maintaining Focus: If a user veers off-topic, politely redirect the conversation back to the company being served in the training data, with a friendly, understanding tone. Use phrases like "I appreciate your interest in [unrelated topic], but let's focus on how I can help you with [something related to the products and services the company provides]" to keep the discussion on track.

3. Exclusive Reliance on Training Data: Lean on your extensive knowledge base to answer user queries. If a question falls outside your training, use a warm, encouraging fallback response like "I'm sorry, I don't have information on that specific topic. Can you rephrase the question please?"

3. Handling Unanswerable Queries: If you encounter a question that cannot be answered using the provided training data, or if the query falls outside your role as a helpful, charismatic, friendly and enthusiastic support agent, politely inform the user that you don't have the necessary information to provide an accurate response. Then, if contact information for the company is available in the training data, provide them with a company email or phone number for further assistance. Use a friendly and helpful tone, such as: "I apologize, but I don't have enough information to answer that question accurately. I recommend reaching out to [company name] at [company email if in the training data] or [company phone if in the training data] for assistance with this request!"

6. Use very few emojis.'''


    def __init__(self, openai_client=None, pinecone_client=None):
        """Initialize the chat handler with optional API clients"""
        self.conversation_history = []  # Start with empty history
        self.max_history = 5  # Keep last 5 exchanges for context
        self.current_namespace = None  # Track current company namespace
        
        # Initialize clients if not provided
        self.openai_client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.pinecone_client = pinecone_client or Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        
        # Constants for Pinecone
        self.PINECONE_INDEX = "all-companies"
        self.PINECONE_HOST = "https://all-companies-6ctd3g7.svc.aped-4627-b74a.pinecone.io"

    def get_relevant_context(self, query: str, namespace: str, num_results: int = 3) -> str:
        """
        Search Pinecone for relevant context based on the query.
        Returns concatenated context strings from top matches.
        """
        try:
            # Get embedding for the query
            query_embedding = self.openai_client.embeddings.create(
                input=query,
                model="text-embedding-ada-002"
            ).data[0].embedding

            # Search Pinecone
            index = self.pinecone_client.Index(self.PINECONE_INDEX)
            results = index.query(
                vector=query_embedding,
                namespace=namespace,
                top_k=num_results,
                include_metadata=True
            )

            # Combine the relevant chunks
            context_chunks = [match.metadata['text'] for match in results.matches]
            return "\n".join(context_chunks)
        except Exception as e:
            print(f"Error getting relevant context: {e}")
            return ""

    def update_company_context(self, new_namespace: str):
        """
        Update the company context and reset history if company changes.
        This ensures conversations don't mix between different companies.
        """
        if new_namespace != self.current_namespace:
            self.reset_conversation()
            self.current_namespace = new_namespace

    def format_messages(self, user_message: str, namespace: str = "", context: str = "") -> List[Dict[str, str]]:
        """
        Format the conversation into messages for the API call.
        Only includes system prompt at start of conversation.
        """
        # Check if company context has changed
        if namespace:
            self.update_company_context(namespace)
        
        messages = []
        
        # Always include system prompt first
        messages.append({"role": "system", "content": self.SYSTEM_PROMPT})
        
        # Add context for this specific question if needed
        if namespace:
            relevant_context = self.get_relevant_context(user_message, namespace)
            if relevant_context:
                messages.append({
                    "role": "system", 
                    "content": f"Context for this question:\n{relevant_context}"
                })
        elif context:
            messages.append({
                "role": "system",
                "content": f"Context for this question:\n{context}"
            })
        
        # Add conversation history
        history_messages = [
            msg for msg in self.conversation_history
            if msg["role"] in ["user", "assistant"]
        ][-self.max_history * 2:]  # Keep only recent messages within max_history
        messages.extend(history_messages)
            
        # Add the current user message
        messages.append({"role": "user", "content": user_message})
        
        # Log the full prompt
        self.log_prompt(messages)

        return messages

    def add_to_history(self, role: str, content: str):
        """
        Add a message to the conversation history with timestamp.
        Maintains history within max_history limit.
        """
        # Add message with timestamp
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only recent messages within max_history limit
        if len(self.conversation_history) > self.max_history * 2:
            # Filter to keep only user and assistant messages
            history_messages = [
                msg for msg in self.conversation_history
                if msg["role"] in ["user", "assistant"]
            ]
            # Keep only the most recent messages based on max_history
            self.conversation_history = history_messages[-self.max_history * 2:]

    def reset_conversation(self):
        """Reset the conversation history"""
        self.conversation_history = []

    def get_response_format_instructions(self) -> str:
        """Get formatting instructions for the response"""
        return '''Format your response according to prompt instructions.'''

    def log_prompt(self, messages: List[Dict[str, str]]):
        """
        Log the prompt to the terminal and a file for debugging.
        Includes timestamp for tracking conversation flow.
        """
        prompt_log = json.dumps(messages, indent=2)  # Pretty-print messages
        
        # Log to terminal
        print(f"\n*** Prompt Used for Model Call ***\n{prompt_log}\n")
        
        # Log to a file
        with open("prompt_log.txt", "a") as log_file:
            log_file.write(f"\n*** Prompt Used at {datetime.now().isoformat()} ***\n")
            log_file.write(prompt_log + "\n")