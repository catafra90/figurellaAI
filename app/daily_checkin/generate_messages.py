from transformers import pipeline
from mock_data import mock_clients

# Load model
generator = pipeline("text2text-generation", model="google/flan-t5-base")

# Generate messages
for client in mock_clients:
    prompt = (
        f"Write a warm and professional follow-up email to {client['name']} after their fitness consultation. "
        "Thank them for attending, encourage them to continue their health journey, and invite them to reach out with questions."
    )

    result = generator(
        prompt,
        max_new_tokens=80,
        do_sample=True,
        temperature=0.8,
        repetition_penalty=1.3,
        top_k=40,
        top_p=0.92
    )[0]['generated_text']

    print(f"To: {client['email']}")
    print(f"Message: {result.strip()}")
    print("-" * 50)




