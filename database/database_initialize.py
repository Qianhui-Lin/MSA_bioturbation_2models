from pymongo import MongoClient
# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
soil_db = client['soil_database']
plotting_db = client['plotting_database']


# Clear existing collections

soil_db['soil_profiles'].delete_many({})
plotting_db['plotting'].delete_many({})

print("Database has been initialized and collections cleared.")