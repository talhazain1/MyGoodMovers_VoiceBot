import openai
import numpy as np
import json
import os

class FAQManager:
    def __init__(self, embedding_model="text-embedding-ada-002"):
        """
        Initialize the FAQManager with the specified OpenAI embedding model.
        It will hold the FAQ data and the corresponding precomputed embeddings.
        """
        self.embedding_model = embedding_model
        self.faq_data = []
        self.embeddings = []

    def load_faqs(self, dataset_path, cache_path="faq_embeddings.npy"):
        """
        Load FAQs from a dataset (assumed to be in JSONL format, one JSON per line)
        and precompute or load cached embeddings.

        :param dataset_path: Path to the FAQ dataset file.
        :param cache_path: Path to a file where embeddings are cached.
        """
        # Load FAQ entries from the dataset
        self.faq_data = []
        with open(dataset_path, "r") as file:
            for line in file:
                try:
                    entry = json.loads(line)
                    if "question" in entry and "answer" in entry:
                        self.faq_data.append(entry)
                except json.JSONDecodeError:
                    print(f"Skipping invalid JSON: {line}")

        # Load cached embeddings if available; otherwise compute and save them
        if os.path.exists(cache_path):
            self.embeddings = np.load(cache_path)
        else:
            self.embeddings = [self.get_embedding(faq["question"]) for faq in self.faq_data]
            np.save(cache_path, self.embeddings)

    def get_embedding(self, text):
        """
        Get the embedding for a given text using OpenAI's embedding API.
        Raises an error if the text is empty.
        
        :param text: The text to embed.
        :return: A numpy array representing the embedding.
        """
        if not text.strip():
            raise ValueError("Input text is empty.")
        response = openai.Embedding.create(
            model=self.embedding_model,
            input=text
        )
        if "data" not in response or not response["data"]:
            raise RuntimeError("Failed to fetch embedding from OpenAI.")
        return np.array(response["data"][0]["embedding"])

    def find_best_match(self, user_question):
        """
        Given a user's question, compute its embedding and then calculate cosine similarity
        with all FAQ question embeddings. Returns the answer of the best match if the similarity
        exceeds a threshold; otherwise, returns a fallback message.
        
        :param user_question: The user's query text.
        :return: The best matching FAQ answer or a fallback message.
        """
        user_embedding = self.get_embedding(user_question)

        # Compute cosine similarities between the user embedding and all FAQ embeddings
        similarities = [
            np.dot(user_embedding, faq_embedding) /
            (np.linalg.norm(user_embedding) * np.linalg.norm(faq_embedding))
            for faq_embedding in self.embeddings
        ]

        best_match_idx = np.argmax(similarities)
        best_match_score = similarities[best_match_idx]

        threshold = 0.75  # You can adjust this threshold based on your needs
        if best_match_score > threshold:
            return self.faq_data[best_match_idx]["answer"]

        # Fallback response if no FAQ is a close match
        return "I'm sorry, I couldn't find an exact match. Could you provide more details?"
