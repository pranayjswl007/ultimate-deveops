Account acc = new Account(Name='Test Account');
insert acc;
System.debug(LoggingLevel.DEBUG, 'Account created with ID: ' + acc.Id);