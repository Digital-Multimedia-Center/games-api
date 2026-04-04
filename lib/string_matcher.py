from sentence_transformers import SentenceTransformer, util
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
            if hit['score'] < threshold: continue
            
            idx = hit['corpus_id']
            candidate_id = self.platform_map[idx]
            candidate_name = self.corpus_strings[idx]
            candidate_ver = self.get_version(candidate_name)
            
            # Version Lock: Numbers must match exactly
            if input_ver != candidate_ver:
                continue
                
            return candidate_id
            
        return -1