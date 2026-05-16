@echo off
pushd "%~dp0.."
python -m app.n1_report_ppt %*
popd
