import os
import sys
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))

# Load env
load_dotenv()

def test_multimodal():
    print("Testing multimodal capability with public URL...")
    
    if os.getenv("GOOGLE_API_KEY"):
        print("Using Google Gemini...")
        try:
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            print("Available models:")
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    print(m.name)
        except Exception as e:
            print(f"Error listing models: {e}")

        from langchain_google_genai import ChatGoogleGenerativeAI
        # Use a model from the available list
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")
    elif os.getenv("OPENAI_API_KEY"):
        print("Using OpenAI GPT-4o...")
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4o")
    else:
        print("No API keys found (GOOGLE_API_KEY or OPENAI_API_KEY)")
        return

    image_url = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQT2W0Rl-bvepwuxdB-cZVj1sh-zzV6qfxfFw&s"
    
    message = HumanMessage(
        content=[
            {"type": "text", "text": "¿Qué ves en esta imagen?"},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
    )
    
    try:
        response = llm.invoke([message])
        print("\nResponse:")
        print(response.content)
        print("\nSUCCESS: Model successfully interpreted the image from public URL.")
    except Exception as e:
        print(f"\nERROR: {e}")

if __name__ == "__main__":
    test_multimodal()