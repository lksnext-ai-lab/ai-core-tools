from collections import Counter
import requests
from bs4 import BeautifulSoup

def remove_duplicates_and_sort(arr):
    # Count the frequency of items in the array
    counts = Counter(arr)
    
    # Remove repetitions and sort the array by frequency
    sorted_arr = sorted(counts, key=lambda x: counts[x], reverse=True)
    return sorted_arr

def get_text_from_url( url, tag="body", id=None, class_name=None):
        attrDict = {}
        if id:
            attrDict["id"] = id
        if class_name:
            attrDict["class"] = class_name
        
        print(f"Getting text from {url} with tag {tag} and attrs {attrDict}")

        try:
            response = requests.get(url, verify=False)
            soup = BeautifulSoup(response.content, "html.parser")
            main_content = soup.find(tag, attrs=attrDict)
            if main_content == None:
                print("WARNING: No main content found")
                return ""
            #print(main_content.get_text())
            print(len(main_content.get_text()))
            return main_content.get_text()
        except Exception as e:
            print(e)
            return ""
