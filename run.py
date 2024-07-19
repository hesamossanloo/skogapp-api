from app import app

if __name__ == "__main__":
    app.run(debug=True)

# Lambda handler
def lambda_handler(event, context):
    import awsgi
    return awsgi.response(app, event, context)
