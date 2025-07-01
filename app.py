from flask import Flask, render_template, request, redirect, session, flash, jsonify
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import os

# Flask App Setup
app = Flask(__name__)
app.secret_key = 'c77b1db2ce6eb9ef49d8cd79443f350b96aec01bfb5bbb20939d83bb0c50898c'

# MongoDB Atlas Setup (your real password included here)
client = MongoClient("mongodb+srv://likhithachalla33:mRm5pfiNwF3pvuKn@cluster0.4khpsn1.mongodb.net/")
db = client['Travelgo']
users_collection = db['users']
bookings_collection = db['bookings']

@app.route('/')
def home():
    return render_template('index.html', logged_in='user' in session)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        if users_collection.find_one({"email": email}):
            return render_template('register.html', message="User already exists.")
        users_collection.insert_one({
            "email": email,
            "name": request.form['name'],
            # Remove the phone line
            "password": generate_password_hash(request.form['password']),
            "logins": 0
        })
        flash("Registration successful! Please login.", "success")
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users_collection.find_one({"email": email})
        if user and check_password_hash(user['password'], password):
            session['user'] = email
            session['user_name'] = user['name']
            users_collection.update_one({"email": email}, {"$inc": {"logins": 1}})
            flash("Login successful! Welcome back.", "success")
            return redirect('/dashboard')
        flash("Invalid email or password. Please try again.", "error")
        return redirect('/login')

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        flash("Please login to access dashboard.", "error")
        return redirect('/login')
    
    email = session['user']
    user = users_collection.find_one({"email": email})
    bookings = list(bookings_collection.find({'user_email': email}))
    
    # Calculate stats
    total_bookings = len(bookings)
    cities_visited = len(set([booking.get('destination', 'Unknown') for booking in bookings]))
    
    return render_template('dashboard.html', 
                         name=user['name'], 
                         bookings=bookings,
                         total_bookings=total_bookings,
                         cities_visited=cities_visited)

@app.route('/cancel', methods=['POST'])
def cancel_booking():
    if 'user' not in session:
        return redirect('/login')
    
    booking_id = request.form.get('booking_id')
    user_email = session['user']
    
    try:
        # Delete the booking from database
        result = bookings_collection.delete_one({
            '_id': ObjectId(booking_id),
            'user_email': user_email
        })
        
        if result.deleted_count > 0:
            flash("Booking cancelled successfully!", "success")
        else:
            flash("Booking not found or already cancelled.", "error")
    except Exception as e:
        flash("Error cancelling booking. Please try again.", "error")
    
    return redirect('/dashboard')

# Booking routes
@app.route('/bus')
def bus_booking():
    if 'user' not in session:
        flash("Please login to book tickets.", "error")
        return redirect('/login')
    return render_template('bus.html')

@app.route('/train')
def train_booking():
    if 'user' not in session:
        flash("Please login to book tickets.", "error")
        return redirect('/login')
    return render_template('train.html')

@app.route('/flight')
def flight_booking():
    if 'user' not in session:
        flash("Please login to book tickets.", "error")
        return redirect('/login')
    return render_template('flight.html')

@app.route('/hotel')
def hotel_booking():
    if 'user' not in session:
        flash("Please login to book tickets.", "error")
        return redirect('/login')
    return render_template('hotel.html')

# Sample booking creation routes (you can expand these)
@app.route('/book_bus', methods=['POST'])
def book_bus():
    if 'user' not in session:
        return redirect('/login')
    
    booking_data = {
        'user_email': session['user'],
        'type': 'Bus',
        'from': request.form.get('from'),
        'to': request.form.get('to'),
        'date': request.form.get('date'),
        'seat': request.form.get('seat'),
        'price': request.form.get('price'),
        'status': 'Confirmed'
    }
    
    bookings_collection.insert_one(booking_data)
    flash("Bus ticket booked successfully!", "success")
    return redirect('/dashboard')

@app.route('/book_train', methods=['POST'])
def book_train():
    if 'user' not in session:
        return redirect('/login')
    
    booking_data = {
        'user_email': session['user'],
        'type': 'Train',
        'from': request.form.get('from'),
        'to': request.form.get('to'),
        'date': request.form.get('date'),
        'seat': request.form.get('seat'),
        'price': request.form.get('price'),
        'status': 'Confirmed'
    }
    
    bookings_collection.insert_one(booking_data)
    flash("Train ticket booked successfully!", "success")
    return redirect('/dashboard')

@app.route('/book_flight', methods=['POST'])
def book_flight():
    if 'user' not in session:
        return redirect('/login')
    
    booking_data = {
        'user_email': session['user'],
        'type': 'Flight',
        'from': request.form.get('from'),
        'to': request.form.get('to'),
        'date': request.form.get('date'),
        'seat': request.form.get('seat'),
        'price': request.form.get('price'),
        'status': 'Confirmed'
    }
    
    bookings_collection.insert_one(booking_data)
    flash("Flight ticket booked successfully!", "success")
    return redirect('/dashboard')

@app.route('/book_hotel', methods=['POST'])
def book_hotel():
    if 'user' not in session:
        return redirect('/login')
    
    booking_data = {
        'user_email': session['user'],
        'type': 'Hotel',
        'location': request.form.get('location'),
        'checkin': request.form.get('checkin'),
        'checkout': request.form.get('checkout'),
        'room': request.form.get('room'),
        'price': request.form.get('price'),
        'status': 'Confirmed'
    }
    
    bookings_collection.insert_one(booking_data)
    flash("Hotel booked successfully!", "success")
    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
