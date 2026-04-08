"""
Semantic matching utilities for game titles and platforms using Sentence Transformers.

This module provides classes to reconcile local library metadata with 
external database (IGDB) records via vector embeddings and cosine similarity.

Author: Amrit Srivastava
"""

from sentence_transformers import SentenceTransformer, util
import torch
import re

class PlatformMatcher:
    """
    Handles mapping of platform strings to verified platform IDs.
    Uses semantic search combined with exact version matching (e.g., distinguishing Xbox vs Xbox 360).
    """
    def __init__(self, platform_data):
        """
        Initializes the transformer model and builds a corpus of platform names.
        
        Args:
            platform_data (list): List of platform dictionaries from the database.
        """
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.platform_map = []
        self.corpus_strings = []

        # Map IDs to searchable strings (names, abbreviations, and alternatives)
        for data in platform_data:
            p_id = data["_id"]
            options = [data["name"], data.get("abbreviation")]
            if data.get("alternative_name"):
                options.extend([s.strip() for s in data["alternative_name"].split(',')])

            for opt in options:
                if opt:
                    self.corpus_strings.append(opt.lower())
                    self.platform_map.append(p_id)

        # Pre-calculate embeddings for the search space
        self.corpus_embeddings = self.model.encode(self.corpus_strings, convert_to_tensor=True)

    def clean(self, text):
        """
        Removes URLs, brackets, and common gaming noise words (e.g., 'Edition') 
        to isolate the core platform or title name.
        """
        text = re.sub(r'http\S+|\[.*?\]|\$\d+|gcipplatform', '', text)
        noise = r'\b(edition|anniversary|deluxe|collector\'s|standard|version|launch|limited|special|complete|gold|ultimate|director\'s cut)\b'
        return re.sub(noise, '', text, flags=re.IGNORECASE).strip().lower()

    def get_version(self, text):
        """
        Extracts version-specific identifiers to prevent false positives between 
        different console generations.
        """
        match = re.search(r'\b(\d+|one|series|vita|portable)\b', text.lower())
        return match.group(1) if match else None

    def match(self, input_str, threshold=0.75):
        """
        Performs semantic search to find the best platform match.
        
        Args:
            input_str (str): The platform name from the local catalog.
            threshold (float): Minimum cosine similarity score to consider a match.
            
        Returns:
            int: The platform ID if a match is found, otherwise -1.
        """
        cleaned_input = self.clean(input_str)
        if not cleaned_input:
            return -1

        input_ver = self.get_version(cleaned_input)

        # Find top 5 semantic candidates
        query_embedding = self.model.encode(cleaned_input, convert_to_tensor=True)
        hits = util.semantic_search(query_embedding, self.corpus_embeddings, top_k=5)[0]

        for hit in hits:
            if hit['score'] < threshold:
                continue

            idx = int(hit['corpus_id'])
            candidate_id = self.platform_map[idx]
            candidate_name = self.corpus_strings[idx]
            candidate_ver = self.get_version(candidate_name)

            # Version Lock: Ensure version numbers match exactly (e.g., PS1 != PS2)
            if input_ver != candidate_ver:
                continue

            return candidate_id

        return -1

class GameTitleMatcher:
    """
    Reconciles local game titles (including variants) with potential IGDB candidates.
    """
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)

    def match(self, local_titles, igdb_candidates):
        """
        Determines the best match from IGDB based on the mean similarity 
        across multiple local title variations (main title, alt titles).

        Args:
            local_titles (list): List of title strings from the local record.
            igdb_candidates (list): List of game dictionaries from IGDB.

        Returns:
            tuple: (best_match_dict, score)
        """
        igdb_names = [game["name"] for game in igdb_candidates]

        # Generate embeddings for both sets
        local_embeddings = self.model.encode(local_titles, convert_to_tensor=True)
        igdb_embeddings = self.model.encode(igdb_names, convert_to_tensor=True)

        # Calculate similarity matrix
        cosine_scores = util.cos_sim(local_embeddings, igdb_embeddings)

        # Average similarity scores across all local titles for each candidate
        candidate_mean_scores = torch.mean(cosine_scores, dim=0)

        best_igdb_idx = int(torch.argmax(candidate_mean_scores).item())
        best_match = igdb_candidates[best_igdb_idx]
        best_score = candidate_mean_scores[best_igdb_idx].item()

        return best_match, best_score
