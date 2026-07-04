def broker_environment_from_name(broker_name: str) -> str:
    return broker_name.split('_')[-1]
