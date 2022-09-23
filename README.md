# Xcalscan: xcalibyte scan service
xcalscan is a web service which is a wrapper for scan engine.


## Working with the git version of xcalscan
xcalscan contains a submodule, "commondef". See: https://github.com/xcalcc/python-common-def.git. This submodule contains some common function implementations.

Due to the way git submodules work, when you clone xcalscan, use below command:
```
git clone --recursive https://github.com/xcalcc/scan-service.git
```

Or you scan clone xcalscan by using:
```
git clone https://github.com/xcalcc/scan-service.git
cd xcalscan
git submodule update --init --recursive
```

