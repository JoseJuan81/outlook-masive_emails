FROM python:3.10.9-windowsservercore-ltsc2022

WORKDIR /app

COPY container/requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./container/main.py" ]