"""Azure OpenAI text embedding generator."""

from typing import List
import openai
from tenacity import retry, stop_after_attempt, wait_exponential


class OpenAIEmbedder:
    """Generate text embeddings using Azure OpenAI."""
    
    def __init__(
        self, 
        api_key: str, 
        endpoint: str, 
        deployment: str = "text-embedding-3-small",
        dimensions: int = 1536
    ):
        """Initialize embedder.
        
        Args:
            api_key: Azure OpenAI API key
            endpoint: Azure OpenAI endpoint
            deployment: Embedding model deployment name
            dimensions: Embedding dimensions (1536 for text-embedding-3-small)
        """
        self.client = openai.AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version="2023-05-15"
        )
        self.deployment = deployment
        self.dimensions = dimensions
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        response = self.client.embeddings.create(
            model=self.deployment,
            input=text[:8000]  # Token limit safety
        )
        return response.data[0].embedding[:self.dimensions]
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def embed_batch(self, texts: List[str], batch_size: int = 16) -> List[List[float]]:
        """Generate embeddings for batch of texts.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call
            
        Returns:
            List of embedding vectors
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            # Truncate texts to token limit
            batch = [t[:8000] for t in batch]
            
            response = self.client.embeddings.create(
                model=self.deployment,
                input=batch
            )
            
            embeddings = [e.embedding[:self.dimensions] for e in response.data]
            all_embeddings.extend(embeddings)
        
        return all_embeddings
