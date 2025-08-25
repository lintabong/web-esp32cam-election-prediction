

def get_candidate_map(db):
    candidates_docs = db.collection('candidates').get()
    CANDIDATE_MAP = {
        doc.id: doc.to_dict().get(
            'label', f'Candidate-{doc.id}') 
            for doc in candidates_docs
        }

    return CANDIDATE_MAP
