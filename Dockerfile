FROM python:3
COPY checkhost-exporter.py /checkhost-exporter.py
COPY requirements.txt /requirements.txt
RUN pip3 install -r requirements.txt
CMD ["python3", "/checkhost-exporter.py"]
