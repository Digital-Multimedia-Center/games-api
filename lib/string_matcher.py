from sentence_transformers import SentenceTransformer, util
import torch
import re

class PlatformMatcher:
    def __init__(self, platform_data):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.platform_map = []
        self.corpus_strings = []

        # Build search space from IGDB JSON
        for data in platform_data:
            p_id = data["_id"]
            options = [data["name"], data.get("abbreviation")]
            if data.get("alternative_name"):
                options.extend([s.strip() for s in data["alternative_name"].split(',')])

            for opt in options:
                if opt:
                    self.corpus_strings.append(opt.lower())
                    self.platform_map.append(p_id)

        self.corpus_embeddings = self.model.encode(self.corpus_strings, convert_to_tensor=True)

    def clean(self, text):
        text = re.sub(r'http\S+|\[.*?\]|\$\d+|gcipplatform', '', text)
        noise = r'\b(edition|anniversary|deluxe|collector\'s|standard|version|launch|limited|special|complete|gold|ultimate|director\'s cut)\b'
        return re.sub(noise, '', text, flags=re.IGNORECASE).strip().lower()

    def get_version(self, text):
        match = re.search(r'\b(\d+|one|series|vita|portable)\b', text.lower())
        return match.group(1) if match else None

    def match(self, input_str, threshold=0.75):
        cleaned_input = self.clean(input_str)
        if not cleaned_input:
            return -1

        input_ver = self.get_version(cleaned_input)

        # Vector search
        query_embedding = self.model.encode(cleaned_input, convert_to_tensor=True)
        hits = util.semantic_search(query_embedding, self.corpus_embeddings, top_k=5)[0]

        for hit in hits:
            if hit['score'] < threshold:
                continue

            idx = hit['corpus_id']
            candidate_id = self.platform_map[idx]
            candidate_name = self.corpus_strings[idx]
            candidate_ver = self.get_version(candidate_name)

            # Version Lock: Numbers must match exactly
            if input_ver != candidate_ver:
                continue

            return candidate_id

        return -1

class GameTitleMatcher:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)

    def match(self, local_titles, igdb_candidates):
        igdb_names = [game["name"] for game in igdb_candidates]

        local_embeddings = self.model.encode(local_titles, convert_to_tensor=True)
        igdb_embeddings = self.model.encode(igdb_names, convert_to_tensor=True)

        cosine_scores = util.cos_sim(local_embeddings, igdb_embeddings)

        candidate_mean_scores = torch.mean(cosine_scores, dim=0)

        best_igdb_idx = torch.argmax(candidate_mean_scores).item()
        best_match = igdb_candidates[best_igdb_idx]
        best_score = candidate_mean_scores[best_igdb_idx].item()

        return best_match, best_score