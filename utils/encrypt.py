from distutils.core import setup
from distutils.extension import Extension
from Cython.Build import cythonize

if __name__ == '__main__':
	team = input('Team Name: ')
	filename = "./src/{}/main.py".format(team)

	setup(
		name=team,
		ext_modules=cythonize([filename], language_level=3),
	)