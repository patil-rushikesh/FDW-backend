from flask import Flask
from flask_pymongo import PyMongo

mongo = PyMongo()

department_collections = {
    'Computer': mongo.db.computer,
    'IT': mongo.db.it,
    'EnTC': mongo.db.entc,
    'Mechanical': mongo.db.mechanical,
    'Civil': mongo.db.civil,
    'AI&DS': mongo.db.aids,
    'FE': mongo.db.fe
}