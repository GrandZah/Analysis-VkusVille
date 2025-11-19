from settings.paths import ConfigPaths, load_config_paths

CONFIG_PATHS: ConfigPaths = load_config_paths()
RUN_TS: str = CONFIG_PATHS.run_log_dir.name
