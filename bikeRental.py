import datetime

class BikeRental:
    def __init__(self,stock=0):
        self.stock = stock
        
    def displaystock(self):
        print("we have currently {} bikes to rent".format(self.stock))
        return self.stock
    
    def rentbikeonhourlybasis(self,n):
        if n <= 0:
            print("number of bikes should be positive")
            return None
        elif n > self.stock:
            print("Sorry!Currently we have {} bikes to rent".format(self.stock))
            return None
        else:
            now = datetime.datetime.now()
            print("you are rented a {} bikes today on hourly basis at {}".format(n,now.hour))
            print("you will be charged $5 for each hour per bike")
            print("hope you enjoy our services")
            
            self.stock -= n
            return now
        
    def rentbikeondailybasis(self,n):
        if n <= 0:
            print("number of bikes should be positive")
            return None
        elif n > self.stock:
            print("Sorry!Currently we have {} bikes to rent".format(self.stock))
            return None
        else:
            now = datetime.datetime.now()
            print("you are rented a {} bikes today on daily basis at {}".format(n,now.hour))
            print("you will be charged $20 for each day per bike")
            print("hope you enjoy our services")
            
            self.stock -= n
            return now
        
    def rentbikeonweeklybasis(self,n):
        if n <= 0:
            print("number of bikes should be positive")
            return None
        elif n > self.stock:
            print("Sorry!Currently we have {} bikes to rent".format(self.stock))
            return None
        else:
            now = datetime.datetime.now()
            print("you are rented a {} bikes today on weekly basis at {}".format(n,now.hour))
            print("you will be charged $60 for each week per bike")
            print("hope you enjoy our services")
            
            self.stock -= n
            return now
        
    def returnbike(self,request):
        
        rentalTime,rentalBasis,numOfbikes = request
        
        
        if rentalTime and rentalBasis and numOfbikes:
            self.stock += numOfbikes
            now = datetime.datetime.now()
            rentalperiod = now - rentalTime
            
            
            if rentalBasis == 1:
                bill = round(rentalperiod.seconds/3600)*5*numOfbikes
        
            elif rentalBasis == 2:
                bill = round(rentalperiod.days)*20*numOfbikes
        
            elif rentalBasis == 3:
                bill = round(rentalperiod.days/7)*60*numOfbikes
            
            if(3 <= numOfbikes <= 5):
                print("youre eligible for discount of 30%")
                bill = bill * 0.7
            
        
            print("total bill is {}".format(bill))
        
            return bill
    
        else:
            print("are u sure u rented a bike with us?")
            return None
        

        
class Customer:
    def __init__(self):
        self.bikes = 0
        self.rentalBasis = 0
        self.rentalTime = 0
        self.bill = 0
        
    def requestbike(self):
        bikes = input("how many bikes you want for rent?")
        
        try:
            bikes = int(bikes)
        except ValueError:
            print("What you entered is not an positive integer")
            return -1
        
        if bikes < 0:
            print("number of bikes entered must be positive")
            return -1
        
        else:
            self.bikes = bikes
            
        return self.bikes
    
    def returnbike(self):
        if self.rentalBasis and self.rentalTime and self.bikes:
            return self.rentalTime,self.rentalBasis,self.bikes
        else:
            return 0,0,0
            
        
    
#shop = BikeRental(100)
#print(shop.stock)


#print(shop.displaystock())

#print(shop.rentbikeonhourlybasis(6))
#print(shop.stock)
    