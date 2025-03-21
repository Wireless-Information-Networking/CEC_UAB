from flask import Blueprint, request, jsonify, render_template
import app.models.ENTSOE_models as ENTSOE_models
from app.config import Config
from app.controllers.CEC_controller import get_surplus_aux
from app.models.CEC_model import RedisModel
from app.aux.aux_modules.logging_helper import log_message
from app.models.ENTSOE_models import sell_by_hours
from datetime import datetime
import sys

MODULE_TYPE = "controller"
MODULE_NAME = "advice"
MODULE_DEBUG = 1

advice_bp = Blueprint('advice', __name__)
redis_model = RedisModel()

def hour_value_to_list(surplus):
    surplus_list = []
    for value in surplus.values():
        surplus_list.append(value)
    return surplus_list

def get_money_advice(
    user_email: str, country:str, fee: str, fixed_value:int,
    has_battery: bool, battery_capacity_kwh: int
    )->str:
    try:
            existing_data = redis_model.get_user(user_email)
            if Config.DEBUG and MODULE_DEBUG and 1:
                log_message("debug", MODULE_TYPE, MODULE_NAME, "get_money_advice", f"Data got from BD: \n {existing_data}")
            
            if existing_data is None:
                log_message("error", MODULE_TYPE, MODULE_NAME, "get_money_advice", f"User not registered")
                return "error", "User is not registeresd"
            else:
                surplus = get_surplus_aux(user_email)
                if Config.DEBUG and MODULE_DEBUG and 1:
                    log_message("debug", MODULE_TYPE, MODULE_NAME, "get_money_advice", f"Surplus as a dict: \n {surplus}")

                surplus = hour_value_to_list(surplus)
                if Config.DEBUG and MODULE_DEBUG and 1:
                    log_message("debug", MODULE_TYPE, MODULE_NAME, "get_money_advice", f"Surplus as a list: \n {surplus}")
        
    except ValueError as e:
        log_message("error", MODULE_TYPE, MODULE_NAME, "get_money_advice", f"Somthing went wrong while pulling data from DB: {e}")
        return "error", e

    # Get price array
    price_list = ENTSOE_models.get_price_array(country, fee, fixed_value)
    if Config.DEBUG and MODULE_DEBUG and 1:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_money_advice", f"Prices as a list: \n {price_list}")

    rent = sell_by_hours(price_list, surplus)
    if Config.DEBUG and MODULE_DEBUG and 1:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_money_advice", f"Surplus x Prices: \n {rent}")

    profit = sum(rent)   
    if Config.DEBUG and MODULE_DEBUG and 1:       
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_money_advice", f"Profitability: \n {profit}")

    if profit > 0:
         return "Sell to the grid", "You will achieve greater profitability if you sell the energy produced during the day instead of storing it in the batteries."
    else:
        if has_battery:
            if (battery_capacity_kwh - sum(surplus)) > 0:
                return "Charge batteries", "You will not achieve greater profitability if you sell the energy produced during the day so better store it for latter"
            else:
                return "Charge batteries", f"You have a surplus of energy, you can charge fully your batteries and consume the {round(sum(surplus)-battery_capacity_kwh, 2)} kWh you will have left."
        else:
            return "Consume more", "You have a surplus of energy, consume more in daytime to avoid wasting it. If you have chores to do, do them now."

def get_co2_advice(
    user_email: str,
    has_battery: bool, battery_capacity_kwh: int
    )->str:
    try:
            existing_data = redis_model.get_user(user_email)
            if Config.DEBUG and MODULE_DEBUG and 1:
                log_message("debug", MODULE_TYPE, MODULE_NAME, "get_co2_advice", f"Data got from BD: \n {existing_data}")
            
            if existing_data is None:
                log_message("error", MODULE_TYPE, MODULE_NAME, "get_co2_advice", f"User not registered")
                return "error", "User is not registeresd"
            else:
                surplus = get_surplus_aux(user_email)
                if Config.DEBUG and MODULE_DEBUG and 1:
                    log_message("debug", MODULE_TYPE, MODULE_NAME, "get_co2_advice", f"Surplus as a dict: \n {surplus}")

                surplus = hour_value_to_list(surplus)
                if Config.DEBUG and MODULE_DEBUG and 1:
                    log_message("debug", MODULE_TYPE, MODULE_NAME, "get_co2_advice", f"Surplus as a list: \n {surplus}")
        
    except ValueError as e:
        log_message("error", MODULE_TYPE, MODULE_NAME, "get_co2_advice", f"Somthing went wrong while pulling data from DB: {e}")
        return "error", e

    balance = sum(surplus)   
    if Config.DEBUG and MODULE_DEBUG and 1:       
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_co2_advice", f"Energy balance: \n {balance}")

    if balance > 0:
         if has_battery:
             if (battery_capacity_kwh - sum(surplus)) > 0:
                 return "Charge batteries", "The last hours are when the dirtiest energy is used. Use your batteries to generate less CO2."
             else:
                 return "Charge batteries", f"You have a surplus of energy, you can charge fully your batteries and consume the {round(sum(surplus)-battery_capacity_kwh, 2)} kWh you will have left."
         else:
            return "Daytime consumption", "You will generate less CO2 if you consume more energy during the day."
    else:
         return "Limit use", "Your production will not cover your consumption, reduce your consumption to not get energy from the grid."

@advice_bp.route('/get_advice', methods=['POST'])
def get_advice():
    # Get necessary data
    try:
        data = request.json
        user_email = data['email']
        country = data['country']
        fee = data['fee']
        fixed_value = data['fixed_price']
        has_battery = data['has_battery']
        battery_capacity_kwh = float(data['battery_capacity'])

    except KeyError as e:
        return jsonify({"error": f"Missing key: {str(e)}"}), 400
    
    money_advice, money_message = get_money_advice(user_email=user_email, country=country, fee=fee, fixed_value=fixed_value,has_battery=has_battery, battery_capacity_kwh=battery_capacity_kwh)
    co2_advice, co2_message =get_co2_advice(user_email=user_email, has_battery=has_battery, battery_capacity_kwh=battery_capacity_kwh)

    if Config.DEBUG and MODULE_DEBUG and 1:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_advice", f"Money advice is {money_advice}")
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_advice", f"CO2 advice is {co2_advice}")

    if money_advice == "error":
        html_content = render_template('error_card.html', error_message=money_message)
    elif co2_advice == "error":
        html_content = render_template('error_card.html', error_message=co2_message)
    else:
        html_content = render_template('advice_flip_card.html', money_advice=money_advice, co2_advice=co2_advice, money_message = money_message, co2_message = co2_message)

    if Config.DEBUG and MODULE_DEBUG and 0:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_advice", f"Advice html: \n {html_content}")

    return html_content

@advice_bp.route('/get_cons_peaks', methods=['POST'])
def get_cons_peaks():
    try:
        data = request.json
        user_email = data['email']

    except KeyError as e:
        return jsonify({"error": f"Missing key: {str(e)}"}), 400 
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    consumption = redis_model.get_consumption_day(user_email, current_date)[0]
    if Config.DEBUG and MODULE_DEBUG and 1:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_cons_peaks", f"Consumption: {consumption}")
    
    if consumption is None:
        return jsonify({"error": "User not registered"}), 400
    
    consumption = hour_value_to_list(consumption)
    
    consumption_mean = sum(consumption)/len(consumption)
    if Config.DEBUG and MODULE_DEBUG and 1:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_cons_peaks", f"Consumption mean: {consumption_mean}")

    surplus = get_surplus_aux(user_email)
    if Config.DEBUG and MODULE_DEBUG and 1:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_cons_peaks", f"Surplus: {surplus}")
    
    peak_hours = []
    threshold = -1*consumption_mean
    for key, value in surplus.items():
        if value < threshold:
            peak_hours.append(key)
    
    if Config.DEBUG and MODULE_DEBUG and 1:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_cons_peaks", f"Peak hours: {peak_hours}")
    
    return jsonify({"peak_hours": peak_hours})

    

