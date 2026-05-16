@echo off
pushd "%~dp0.."
python -m app.n1_report_pack %*
popd
