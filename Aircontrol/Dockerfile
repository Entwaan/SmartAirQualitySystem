# set the kernel to use
FROM python:3.8-alpine
# copy all the files in the container
COPY . .
# install the needed requirements
RUN pip3 install -r requirements.txt
# the command that will be executed when the container will start
CMD ["python3","./aircontrol.py"]