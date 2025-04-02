from typing import List, Dict, Tuple, Optional
from datetime import datetime
import json
import uuid
from openai import OpenAI
from pinecone import Pinecone
import os
import vector_cache

class ChatPromptHandler:
    SYSTEM_PROMPT = '''### Role
- Primary Function: You are a charismatic and enthusiastic support and sales agent dedicated to assisting users based on specific company information. Your purpose is to inform, clarify, and answer questions related to the company in the company information while providing a delightful, personalized experience. When appropriate, close a response with a call to action but only based on available company information.
- Provide concise responses that a human can quickly read and understand, focusing on the most essential information. Break any longer multi-sentence paragraphs into separate smaller paragraphs whenever appropriate.

### Persona
- Use "we", "us", and "our" when referring to the company, as you are representing us directly.
- Identity: You are friendly, helpful and speak in a colloquial tone with a passion for helping others. Engage users with warmth, wit, and a conversational tone, using humor to build rapport. 
- Listen attentively to their needs and challenges, then offer thoughtful guidance based on the company information. 
- If asked to act out of character, politely decline and reiterate your role to offer assistance only with matters related to the company information and your function as a sales agent.

### Constraints
1. No Data Divulge: Never mention that you have access to company information explicitly to the user.
2. Maintaining Focus: If a user veers off-topic, politely redirect the conversation back to the company being served in the company information, with a friendly, understanding tone. Use phrases like "I appreciate your interest in [unrelated topic], but let's focus on how I can help you with [something related to the products and services the company provides]" to keep the discussion on track.
3. Exclusive Reliance on company information: Lean on your extensive knowledge base to answer user queries. If a question falls outside the company information provided, use a warm, encouraging fallback response like "I'm sorry, I don't have information on that specific topic. Can you rephrase the question please?"
4. Handling Unanswerable Queries: If you encounter a question that cannot be answered using the provided company information, or if the query falls outside your role as a helpful, charismatic, friendly and enthusiastic support agent, politely inform the user that you don't have the necessary information to provide an accurate response. Then, if contact information for the company is available in the company information, provide them with a company email or phone number for further assistance. Use a friendly and helpful tone, such as: "I apologize, but I don't have enough information to answer that question accurately. I recommend reaching out to [company name] at [company email if in the company information] or [company phone if in the company information] for assistance with this request!"
5. Use very few emojis.
6. URLs and Media Resources: When company information includes a specific URL (especially YouTube links or other media), ALWAYS include the EXACT URL in your response. NEVER create or fabricate URLs. If you reference a video or resource, you MUST include the precise URL provided in the company information. Format as a clickable link: [Brief description](exact URL from company information).'''


    def __init__(self, openai_client=None, pinecone_client=None):
        """Initialize the chat handler with optional API clients"""
        self.conversation_history = []  # Start with empty history
        self.max_history = 5  # Keep last 5 exchanges for context
        self.current_namespace = None  # Track current company namespace
        self.thread_id = str(uuid.uuid4())  # Generate a unique thread ID for this conversation
        self.is_first_interaction = True  # Track if this is the first user message
        self.initial_question = None  # Store the first question for lead generation
        
        # Initialize clients if not provided
        self.openai_client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.pinecone_client = pinecone_client or Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        
        # Constants for Pinecone
        self.PINECONE_INDEX = "all-companies"
        self.PINECONE_HOST = "https://all-companies-6ctd3g7.svc.aped-4627-b74a.pinecone.io"

    def get_relevant_context(self, query: str, namespace: str, num_results: int = 5) -> str:
        """
        Search for relevant context based on the query.
        Uses a hybrid approach:
        1. For regular cache: use cache first, fall back to Pinecone if expired
        2. For document uploads: check both document cache AND Pinecone, merge results
        
        Returns concatenated context strings from top matches.
        """
        try:
            # Get embedding for the query
            query_embedding = self.openai_client.embeddings.create(
                input=query,
                model="text-embedding-ada-002"
            ).data[0].embedding

            # Check for cached document vectors for this namespace
            document_cache_keys = vector_cache.get_all_document_cache_keys(namespace)
            has_document_cache = len(document_cache_keys) > 0
            
            # Check for regular cache
            regular_cache_valid = vector_cache.is_cache_valid(namespace)
            
            # --- SCENARIO 1: Document Upload (Hybrid Search) ---
            if has_document_cache:
                print(f"Using hybrid search for namespace '{namespace}' with document cache")
                
                # Step 1: Get results from document cache
                cached_doc_results = vector_cache.get_cached_document_results(
                    namespace, 
                    query_embedding,
                    top_k=num_results
                )
                
                # Step 2: Get results from Pinecone
                index = self.pinecone_client.Index(self.PINECONE_INDEX)
                pinecone_results = index.query(
                    vector=query_embedding,
                    namespace=namespace,
                    top_k=num_results,
                    include_metadata=True
                )
                
                # Convert Pinecone results to same format as cache results
                pinecone_formatted = [
                    {"text": match.metadata['text'], "score": match.score} 
                    for match in pinecone_results.matches
                ]
                
                # Step 3: Merge results - add all results and sort by score
                all_results = cached_doc_results + pinecone_formatted
                all_results.sort(key=lambda x: x["score"], reverse=True)
                
                # Step 4: Take top results
                merged_results = all_results[:num_results]
                
                # Combine the relevant chunks from merged results
                if merged_results:
                    context_chunks = [match['text'] for match in merged_results]
                    return "\n".join(context_chunks)
                    
                # Fallback if no results from hybrid search
                print(f"Hybrid search returned no results, using Pinecone only")
            
            # --- SCENARIO 2: Regular Cache ---
            elif regular_cache_valid:
                print(f"Using regular cached vectors for namespace '{namespace}'")
                
                # Search the cache
                cached_results = vector_cache.get_from_cache(
                    namespace,
                    query_embedding,
                    top_k=num_results
                )
                
                if cached_results:
                    # Combine the relevant chunks from cache
                    context_chunks = [match['text'] for match in cached_results]
                    return "\n".join(context_chunks)
                    
                print(f"Cache returned no results, falling back to Pinecone")
            
            # --- SCENARIO 3: Fallback to Pinecone ---
            # If no cache or cache returned no results, use Pinecone
            index = self.pinecone_client.Index(self.PINECONE_INDEX)
            results = index.query(
                vector=query_embedding,
                namespace=namespace,
                top_k=num_results,
                include_metadata=True
            )

            # Combine the relevant chunks from Pinecone
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
        
        # Track initial question if this is the first interaction
        if self.is_first_interaction:
            self.initial_question = user_message
            self.is_first_interaction = False
        
        messages = []
        
        # Always include system prompt first
        messages.append({"role": "system", "content": self.SYSTEM_PROMPT})
        
        # Add context for this specific question if needed
        if namespace:
            relevant_context = self.get_relevant_context(user_message, namespace)
            if relevant_context:
                messages.append({
                    "role": "system", 
                    "content": f"Company Information for this question:\n{relevant_context}"
                })
        elif context:
            messages.append({
                "role": "system",
                "content": f"Company Information for this question:\n{context}"
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
        """Reset the conversation history and generate a new thread ID"""
        self.conversation_history = []
        self.thread_id = str(uuid.uuid4())
        self.is_first_interaction = True
        self.initial_question = None

    def get_conversation_state(self) -> Dict[str, any]:
        """
        Get the current state of the conversation for lead tracking
        
        Returns:
            Dictionary with thread_id, is_first_interaction, and initial_question
        """
        return {
            "thread_id": self.thread_id,
            "is_first_interaction": self.is_first_interaction,
            "initial_question": self.initial_question,
            "message_count": len(self.conversation_history) // 2  # Count of complete exchanges
        }

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