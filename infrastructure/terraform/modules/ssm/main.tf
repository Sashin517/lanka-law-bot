# In a real environment, you wouldn't create secrets with dummy values in terraform
# unless you use lifecycle ignore_changes. We'll just define the prefix here.
# The user will run AWS CLI commands to populate them as per the plan.
