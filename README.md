# Sports AI

    ESPN / Cricbuzz  --->  new events  --->  LLM commentary  --->  web page
                              |                    ^
                              |                    |
             milestone? --> player stats before the match (checked) --+
             every 2-5 min --> one fact from the match fact pack -----+
    Question --> understand --> live data + web search --> vector store
             --> grade --> answer --> check --> web page

Run:

    pip install -r requirements.txt
    cp .env.example .env
    uvicorn main:app --port 8080
