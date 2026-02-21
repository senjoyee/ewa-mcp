"""Azure AI Foundry text embedding generator using text-embedding-3-small."""

from typing import List
import openai
from tenacity import retry, stop_after_attempt, wait_exponential


class OpenAIEmbedder:
    """Generate text embeddings using text-embedding-3-small via Azure AI Foundry."""
    
    def __init__(
        self, 
        api_key: str, 
        endpoint: str, 
        deployment: str = "text-embedding-3-small",
        dimensions: int = 1536,
    ):
        """Initialize embedder.
        
        Args:
            api_key: Azure AI Foundry API key
            endpoint: Azure AI Foundry endpoint (e.g., https://<project>.<region>.models.ai.azure.com)
            deployment: Embedding model deployment name
            dimensions: Embedding dimensions (1536 for text-embedding-3-small)
        """
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=endpoint.rstrip("/") + "/"
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
            input=[text[:8000]],  # Token limit safety
            dimensions=self.dimensions
        )
        return response.data[0].embedding
    
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
                input=batch,
                dimensions=self.dimensions
            )
            
            embeddings = [e.embedding for e in response.data]
            all_embeddings.extend(embeddings)
        
        return all_embeddings
