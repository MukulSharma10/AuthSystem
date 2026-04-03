# Voice Based User Authentication System

This project is a basic demonstration of an authentication system that grants access to users based on their voice features.

## Local Development

The flow of the working of the project is as follows-

- Run the development server on your local machine
- Open PgAdmin and connect to the database created earlier for this project
- Open the registration.html page via live server 
- Register your credentials and set up the passphrase
- Open the login.html page via live server
- Enter your credentials and speak your passphrase for a successful login

## Requirements

- Run the following command in your terminal to install the node dependencies in the project

`npm install`

- Run the following command in your terminal to install the python dependencies in the project

`pip install librosa scikit-learn`

- This project requires a connection to a Postgresql database, create the database by running the following command in your PgAdmin dashboard

`CREATE TABLE recordings ( id SERIAL PRIMARY KEY, username TEXT, email TEXT, audio_data BYTEA );`

Also create a .env file in the project directory to set up the necessary PGClient environment variables needed to run the project. You can find the .env template in the .env.example file of the repository

## Features

- Fast and Reliable User Authentication
- Voice based passphrase support
- Multiple audio devices support

## Feedback
For any feedback regarding the project, email me at mukulsharma528491@gmail.com
