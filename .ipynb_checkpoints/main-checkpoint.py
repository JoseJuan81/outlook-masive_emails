from contacts import contacts

class SendEmails:
    contacts = []
    images = {
        body: [],
        sign: [],
    }
    templates = {
        body: "",
        sign: "",
    }
    
    def set_contacts(self, contacts:list):
        self.contacts = contacts
    
        
if __name__ == "__main__":
    
    emails = SendEmails()
    emails.set_contacts(contacts)
    print("email.contacts", email.contacts)
    #emails.set_email_sign()
    #emails.set_body_email()
    #emails.send()