from app import app

if __name__ == "__main__":
    app.run(debug=True)

# Lambda handler
def lambda_handler(event, context):
    from mangum import Mangum
    handler = Mangum(app)
    return handler(event, context)